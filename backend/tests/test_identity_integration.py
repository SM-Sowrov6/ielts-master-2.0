"""Authentication lifecycle against real PostgreSQL + Redis.

Requires TEST_DATABASE_ADMIN_URL and TEST_REDIS_URL.

Emails are delivered by the real outbox Dispatcher into a MemoryEmailSender, and links are taken
from the delivered message text, exactly as a user would follow them.
"""

import asyncio
import hashlib
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.core.email import MemoryEmailSender, OutgoingEmail
from app.core.outbox import OutboxMessage
from app.main import create_app
from app.modules.audit.models import AuditLog
from app.modules.identity.models import (
    AuthSession,
    OneTimeToken,
    Role,
    User,
    UserConsent,
    UserRole,
)
from app.workers.outbox import MAX_ATTEMPTS, Dispatcher

pytestmark = pytest.mark.integration

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
SECRET = "integration-test-secret-key-0123456789"
PASSWORD = "correct horse battery staple 42"
NEW_PASSWORD = "another long passphrase 2026"
TOKEN_RE = re.compile(r"#token=([A-Za-z0-9_-]{43})")
SESSION, CSRF = "ielts_session", "ielts_csrf"


def _settings(database_url: str, redis_url: str, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "ci",
        "database_url": database_url,
        "redis_url": redis_url,
        "auth_secret_key": SECRET,
        "password_hash_memory_kib": 1024,  # fast tests; production enforces >= 19 MiB
        "password_hash_iterations": 1,
        "smtp_host": "smtp.invalid",
        "email_from": "IELTS MASTER <no-reply@example.test>",
        "public_app_url": "http://localhost:3000",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def identity_db(test_database_url: str) -> str:
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["configure_logger"] = False
    cfg.attributes["database_url"] = test_database_url
    command.upgrade(cfg, "head")
    return test_database_url


@pytest.fixture
async def redis_url(test_redis_url: str) -> str:
    """Redis database 15 is reserved for tests and flushed, so rate limits start fresh."""
    url = make_url(test_redis_url).set(database="15").render_as_string(hide_password=False)
    client = Redis.from_url(url)
    await client.flushdb()
    await client.aclose()
    return url


@dataclass
class Env:
    app: FastAPI
    settings: Settings
    outbox: MemoryEmailSender
    dispatcher: Dispatcher

    def browser(self, ip: str = "203.0.113.10") -> Browser:
        return Browser(self.app, ip)

    async def deliver(self) -> list[OutgoingEmail]:
        before = len(self.outbox.sent)
        while await self.dispatcher.process_batch():
            pass
        return self.outbox.sent[before:]

    async def sql(self, statement: Any, params: dict[str, Any] | None = None) -> Any:
        async with self.app.state.db_session_factory() as db, db.begin():
            return await db.execute(statement, params or {})


@pytest.fixture
async def env(identity_db: str, redis_url: str) -> AsyncIterator[Env]:
    settings = _settings(identity_db, redis_url)
    app = create_app(settings)
    sender = MemoryEmailSender()
    # The test database is shared across tests: start each test with an empty outbox.
    async with app.state.db_session_factory() as db, db.begin():
        await db.execute(text("DELETE FROM outbox_messages"))
    yield Env(app, settings, sender, Dispatcher(settings, app.state.db_session_factory, sender))
    await app.state.db_engine.dispose()
    await app.state.redis.aclose()


class Browser:
    """A same-origin browser: keeps cookies and echoes the CSRF cookie like the frontend does."""

    def __init__(self, app: FastAPI, ip: str) -> None:
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=(ip, 50000)),
            base_url="http://localhost:3000",
        )

    async def csrf(self) -> str:
        response = await self.client.get("/api/v1/auth/csrf")
        assert response.status_code == 200
        token: str = response.json()["csrf_token"]
        return token

    async def post(
        self,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        token = self.client.cookies.get(CSRF) or await self.csrf()
        merged = {"X-CSRF-Token": token, **(headers or {})}
        return await self.client.post(f"/api/v1{path}", json=body, headers=merged)

    async def get(self, path: str) -> httpx.Response:
        return await self.client.get(f"/api/v1{path}")

    async def close(self) -> None:
        await self.client.aclose()


def _email() -> str:
    return f"student-{uuid.uuid4().hex[:10]}@example.test"


def _registration(email: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "full_name": "Amina Rahman",
        "email": email,
        "password": PASSWORD,
        "accept_terms": True,
        "age_confirmation": True,
    }
    body.update(overrides)
    return body


def _token(message: OutgoingEmail) -> str:
    match = TOKEN_RE.search(message.text)
    assert match, message.text
    return match.group(1)


async def _register_and_verify(env: Env, email: str | None = None) -> str:
    email = email or _email()
    browser = env.browser(ip=f"198.51.100.{uuid.uuid4().int % 250}")
    assert (await browser.post("/auth/register", _registration(email))).status_code == 202
    (message,) = await env.deliver()
    assert (await browser.post("/auth/verify-email", {"token": _token(message)})).status_code == 204
    await browser.close()
    return email


async def _signed_in(
    env: Env, email: str, password: str = PASSWORD, ip: str | None = None
) -> Browser:
    browser = env.browser(ip=ip or f"192.0.2.{uuid.uuid4().int % 250}")
    response = await browser.post("/auth/login", {"email": email, "password": password})
    assert response.status_code == 200, response.text
    return browser


def _set_cookie_headers(response: httpx.Response) -> list[str]:
    return response.headers.get_list("set-cookie")


# --- Registration & verification -----------------------------------------------------------------
async def test_full_registration_verification_and_login_lifecycle(env: Env) -> None:
    email = _email()
    browser = env.browser()
    response = await browser.post("/auth/register", _registration(email))
    assert response.status_code == 202
    assert response.headers["cache-control"] == "no-store"

    user = (await env.sql(select(User).where(User.email == email))).scalar_one()
    assert user.status == "pending"
    assert user.email_verified_at is None
    assert user.password_hash.startswith("$argon2id$")
    consents = (
        await env.sql(
            select(UserConsent.consent_type, UserConsent.document_version).where(
                UserConsent.user_id == user.id
            )
        )
    ).all()
    assert {c for c, _ in consents} == {"terms", "privacy", "age_confirmation"}
    assert all(v == "dev-placeholder" for _, v in consents)  # no invented policy (D-13/D-17)
    roles = (
        (
            await env.sql(
                select(Role.code)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    assert roles == ["student"]

    # Unverified accounts cannot sign in, but are told why only after a correct password.
    blocked = await browser.post("/auth/login", {"email": email, "password": PASSWORD})
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "email_not_verified"

    (message,) = await env.deliver()
    assert message.to == email
    assert "http://localhost:3000/verify-email#token=" in message.text  # PUBLIC_APP_URL + fragment
    raw = _token(message)
    stored = (
        await env.sql(select(OneTimeToken.token_hash).where(OneTimeToken.user_id == user.id))
    ).scalar_one()
    assert stored == hashlib.sha256(raw.encode()).digest()  # only the hash is stored
    payloads = (await env.sql(select(OutboxMessage.payload))).scalars().all()
    assert all(raw not in str(p) for p in payloads)

    assert (await browser.post("/auth/verify-email", {"token": raw})).status_code == 204
    reused = await browser.post("/auth/verify-email", {"token": raw})
    assert reused.status_code == 400
    assert reused.json()["code"] == "token_invalid"

    login = await browser.post("/auth/login", {"email": email.upper(), "password": PASSWORD})
    assert login.status_code == 200
    me = login.json()
    assert me["email"] == email
    assert me["roles"] == ["student"]
    assert me["permissions"] == []
    assert me["email_verified"] is True
    cookies = _set_cookie_headers(login)
    session_cookie = next(c for c in cookies if c.startswith(f"{SESSION}="))
    csrf_cookie = next(c for c in cookies if c.startswith(f"{CSRF}="))
    assert "HttpOnly" in session_cookie
    assert "SameSite=lax" in session_cookie
    assert "Path=/" in session_cookie
    assert "HttpOnly" not in csrf_cookie
    assert (await browser.get("/me")).json()["full_name"] == "Amina Rahman"
    await browser.close()


async def test_duplicate_registration_is_indistinguishable_and_notifies_owner(env: Env) -> None:
    email = await _register_and_verify(env)
    browser = env.browser()
    fresh = await browser.post("/auth/register", _registration(_email()))
    dup = await browser.post(
        "/auth/register", _registration(email.upper(), full_name="Someone Else")
    )
    assert dup.status_code == fresh.status_code == 202
    assert dup.json() == fresh.json()
    assert (await env.sql(select(User).where(User.email == email))).scalars().all().__len__() == 1
    delivered = await env.deliver()
    notice = next(m for m in delivered if m.to == email)
    assert "already" in notice.subject
    assert "#token=" not in notice.text
    await browser.close()


async def test_resend_supersedes_previous_verification_link(env: Env) -> None:
    email = _email()
    browser = env.browser()
    await browser.post("/auth/register", _registration(email))
    (first,) = await env.deliver()
    assert (await browser.post("/auth/verify-email/resend", {"email": email})).status_code == 202
    (second,) = await env.deliver()
    assert _token(first) != _token(second)
    assert (await browser.post("/auth/verify-email", {"token": _token(first)})).status_code == 400
    assert (await browser.post("/auth/verify-email", {"token": _token(second)})).status_code == 204
    # Unknown addresses get the same answer and no email.
    assert (await browser.post("/auth/verify-email/resend", {"email": _email()})).status_code == 202
    assert await env.deliver() == []
    await browser.close()


async def test_registration_validation(env: Env) -> None:
    browser = env.browser()
    cases: list[tuple[dict[str, Any], int, str]] = [
        (_registration(_email(), password="short"), 422, "password_policy"),
        (_registration(_email(), password="password1234"), 422, "password_policy"),  # blocklist
        (_registration(_email(), accept_terms=False), 422, "consent_required"),
        (_registration(_email(), age_confirmation=False), 422, "consent_required"),
        (_registration("not-an-email"), 422, "validation_error"),
        (_registration(_email(), full_name="   "), 422, "validation_error"),
        ({**_registration(_email()), "role": "admin"}, 422, "validation_error"),  # mass assignment
    ]
    for body, status, code in cases:
        response = await browser.post("/auth/register", body)
        assert (response.status_code, response.json()["code"]) == (status, code), body
        assert PASSWORD not in response.text
        assert "password1234" not in response.text
    await browser.close()


async def test_registration_closed_by_configuration(identity_db: str, redis_url: str) -> None:
    app = create_app(_settings(identity_db, redis_url, registration_enabled=False))
    browser = Browser(app, "203.0.113.20")
    policy = (await browser.get("/auth/registration-policy")).json()
    assert policy["open"] is False
    response = await browser.post("/auth/register", _registration(_email()))
    assert response.status_code == 403
    assert response.json()["code"] == "registration_closed"
    await browser.close()
    await app.state.db_engine.dispose()
    await app.state.redis.aclose()


async def test_approved_minimum_age_is_reported_and_recorded(
    identity_db: str, redis_url: str
) -> None:
    settings = _settings(identity_db, redis_url, registration_minimum_age=16)
    app = create_app(settings)
    sender = MemoryEmailSender()
    env = Env(app, settings, sender, Dispatcher(settings, app.state.db_session_factory, sender))
    browser = env.browser()
    policy = (await browser.get("/auth/registration-policy")).json()
    assert policy["minimum_age"] == 16
    assert policy["development_placeholders"] is True  # legal documents still pending (D-17)
    email = _email()
    assert (await browser.post("/auth/register", _registration(email))).status_code == 202
    user_id = (await env.sql(select(User.id).where(User.email == email))).scalar_one()
    version = (
        await env.sql(
            select(UserConsent.document_version).where(
                UserConsent.user_id == user_id, UserConsent.consent_type == "age_confirmation"
            )
        )
    ).scalar_one()
    assert version == "minimum-age:16"
    await browser.close()
    await app.state.db_engine.dispose()
    await app.state.redis.aclose()


async def test_registration_policy_reports_development_placeholders(env: Env) -> None:
    browser = env.browser()
    policy = (await browser.get("/auth/registration-policy")).json()
    assert policy == {
        "open": True,
        "minimum_age": None,
        "terms_version": "dev-placeholder",
        "privacy_version": "dev-placeholder",
        "development_placeholders": True,
    }
    await browser.close()


# --- Login & sessions ---------------------------------------------------------------------------
async def test_login_failures_are_generic(env: Env) -> None:
    email = await _register_and_verify(env)
    browser = env.browser()
    wrong = await browser.post("/auth/login", {"email": email, "password": "wrong password 123"})
    unknown = await browser.post("/auth/login", {"email": _email(), "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert {k: wrong.json()[k] for k in ("code", "title")} == {
        k: unknown.json()[k] for k in ("code", "title")
    }
    rows = (
        (await env.sql(select(AuditLog).where(AuditLog.action == "identity.login.failed")))
        .scalars()
        .all()
    )
    assert rows
    assert all(email not in str(r.changes) for r in rows)
    assert all(r.ip is None or str(r.ip).endswith("/24") for r in rows)
    await browser.close()


async def test_login_rotates_session_and_revokes_the_previous_one(env: Env) -> None:
    email = await _register_and_verify(env)
    browser = await _signed_in(env, email)
    first = browser.client.cookies.get(SESSION)
    old_csrf = browser.client.cookies.get(CSRF)
    again = await browser.post("/auth/login", {"email": email, "password": PASSWORD})
    assert again.status_code == 200
    second = browser.client.cookies.get(SESSION)
    assert first
    assert second
    assert first != second
    revoked = (
        await env.sql(
            select(AuthSession.revoked_reason).where(
                AuthSession.token_hash == hashlib.sha256(first.encode()).digest()
            )
        )
    ).scalar_one()
    assert revoked == "replaced_by_login"
    # The old CSRF token was bound to the old session and no longer verifies.
    stale = await browser.client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": old_csrf or ""}
    )
    assert stale.status_code == 403
    await browser.close()


async def test_logout_and_logout_all(env: Env) -> None:
    email = await _register_and_verify(env)
    laptop = await _signed_in(env, email)
    phone = await _signed_in(env, email)
    assert (await phone.get("/me")).status_code == 200
    logout = await laptop.post("/auth/logout")
    assert logout.status_code == 204
    assert any(
        c.startswith(f"{SESSION}=") and "Max-Age=0" in c for c in _set_cookie_headers(logout)
    )
    assert (await laptop.get("/me")).status_code == 401
    assert (await phone.get("/me")).status_code == 200  # other device unaffected
    other = await _signed_in(env, email)
    assert (await phone.post("/auth/logout-all")).status_code == 204
    assert (await phone.get("/me")).status_code == 401
    assert (await other.get("/me")).status_code == 401
    for b in (laptop, phone, other):
        await b.close()


async def test_idle_and_absolute_expiry(env: Env) -> None:
    email = await _register_and_verify(env)
    browser = await _signed_in(env, email)
    token_hash = hashlib.sha256(browser.client.cookies[SESSION].encode()).digest()
    await env.sql(
        update(AuthSession)
        .where(AuthSession.token_hash == token_hash)
        .values(idle_expires_at=text("now() - interval '1 second'"))
    )
    assert (await browser.get("/me")).status_code == 401
    browser2 = await _signed_in(env, email)
    token_hash = hashlib.sha256(browser2.client.cookies[SESSION].encode()).digest()
    await env.sql(
        update(AuthSession)
        .where(AuthSession.token_hash == token_hash)
        .values(absolute_expires_at=text("now() - interval '1 second'"))
    )
    assert (await browser2.get("/me")).status_code == 401
    await browser.close()
    await browser2.close()


async def test_idle_window_slides_but_never_past_absolute(env: Env) -> None:
    email = await _register_and_verify(env)
    browser = await _signed_in(env, email)
    token_hash = hashlib.sha256(browser.client.cookies[SESSION].encode()).digest()
    await env.sql(
        update(AuthSession)
        .where(AuthSession.token_hash == token_hash)
        .values(
            last_seen_at=text("now() - interval '1 hour'"),
            idle_expires_at=text("now() + interval '1 minute'"),
            absolute_expires_at=text("now() + interval '2 hours'"),
        )
    )
    assert (await browser.get("/me")).status_code == 200
    row = (
        await env.sql(select(AuthSession).where(AuthSession.token_hash == token_hash))
    ).scalar_one()
    assert row.idle_expires_at == row.absolute_expires_at  # slid forward, capped at absolute
    await browser.close()


async def test_concurrent_requests_share_one_session(env: Env) -> None:
    email = await _register_and_verify(env)
    browser = await _signed_in(env, email)
    responses = await asyncio.gather(*(browser.get("/me") for _ in range(12)))
    assert {r.status_code for r in responses} == {200}
    await browser.close()


async def test_suspension_takes_effect_immediately(env: Env) -> None:
    email = await _register_and_verify(env)
    browser = await _signed_in(env, email)
    await env.sql(update(User).where(User.email == email).values(status="suspended"))
    assert (await browser.get("/me")).status_code == 401
    retry = await browser.post("/auth/login", {"email": email, "password": PASSWORD})
    assert retry.status_code == 401
    assert retry.json()["code"] == "invalid_credentials"
    await browser.close()


# --- CSRF ----------------------------------------------------------------------------------------
async def test_csrf_initialisation_and_rejections(env: Env) -> None:
    email = await _register_and_verify(env)
    browser = env.browser()
    token = await browser.csrf()
    assert browser.client.cookies.get(CSRF) == token
    body = {"email": email, "password": PASSWORD}
    url = "/api/v1/auth/login"

    async def code(response: httpx.Response) -> tuple[int, str]:
        return response.status_code, response.json().get("code", "")

    assert await code(await browser.client.post(url, json=body)) == (403, "csrf_failed")  # missing
    assert await code(
        await browser.client.post(url, json=body, headers={"X-CSRF-Token": token + "x"})
    ) == (403, "csrf_failed")
    forged = await env.browser().csrf()  # valid signature, but not this browser's cookie
    assert await code(
        await browser.client.post(url, json=body, headers={"X-CSRF-Token": forged})
    ) == (403, "csrf_failed")
    for extra in (
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
        {"Origin": "https://evil.example"},
    ):
        response = await browser.client.post(
            url, json=body, headers={"X-CSRF-Token": token, **extra}
        )
        assert await code(response) == (403, "csrf_failed"), extra
    form = await browser.client.post(
        url,
        content=f"email={email}&password=x",
        headers={"X-CSRF-Token": token, "Content-Type": "application/x-www-form-urlencoded"},
    )
    assert await code(form) == (403, "csrf_failed")
    # Registration is protected the same way.
    assert await code(
        await browser.client.post("/api/v1/auth/register", json=_registration(_email()))
    ) == (403, "csrf_failed")
    ok = await browser.client.post(
        url,
        json=body,
        headers={
            "X-CSRF-Token": token,
            "Origin": "http://localhost:3000",
            "Sec-Fetch-Site": "same-origin",
        },
    )
    assert ok.status_code == 200
    await browser.close()


# --- Password reset & change ---------------------------------------------------------------------
async def test_password_reset_lifecycle(env: Env) -> None:
    email = await _register_and_verify(env)
    signed_in = await _signed_in(env, email)
    browser = env.browser()
    assert (await browser.post("/auth/password/forgot", {"email": _email()})).status_code == 202
    assert await env.deliver() == []  # unknown address: same answer, no email
    assert (await browser.post("/auth/password/forgot", {"email": email})).status_code == 202
    (first,) = await env.deliver()
    assert (await browser.post("/auth/password/forgot", {"email": email})).status_code == 202
    (message,) = await env.deliver()
    assert "/reset-password#token=" in message.text
    stale = await browser.post(
        "/auth/password/reset", {"token": _token(first), "new_password": NEW_PASSWORD}
    )
    assert stale.status_code == 400  # superseded by the newer link

    weak = await browser.post(
        "/auth/password/reset", {"token": _token(message), "new_password": "password1234"}
    )
    assert weak.status_code == 422  # rejected password does not burn the link
    done = await browser.post(
        "/auth/password/reset", {"token": _token(message), "new_password": NEW_PASSWORD}
    )
    assert done.status_code == 204
    reused = await browser.post(
        "/auth/password/reset", {"token": _token(message), "new_password": NEW_PASSWORD}
    )
    assert reused.status_code == 400

    assert (await signed_in.get("/me")).status_code == 401  # all sessions revoked
    (notice,) = await env.deliver()
    assert "changed" in notice.subject
    old = await browser.post("/auth/login", {"email": email, "password": PASSWORD})
    assert old.status_code == 401
    new = await browser.post("/auth/login", {"email": email, "password": NEW_PASSWORD})
    assert new.status_code == 200
    await browser.close()
    await signed_in.close()


async def test_password_reset_does_not_verify_email(env: Env) -> None:
    email = _email()
    browser = env.browser()
    await browser.post("/auth/register", _registration(email))
    await env.deliver()  # verification email, deliberately not used
    await browser.post("/auth/password/forgot", {"email": email})
    (reset,) = await env.deliver()
    done = await browser.post(
        "/auth/password/reset", {"token": _token(reset), "new_password": NEW_PASSWORD}
    )
    assert done.status_code == 204
    user = (await env.sql(select(User).where(User.email == email))).scalar_one()
    assert user.status == "pending"
    assert user.email_verified_at is None
    blocked = await browser.post("/auth/login", {"email": email, "password": NEW_PASSWORD})
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "email_not_verified"
    await browser.close()


async def test_expired_tokens_are_rejected(env: Env) -> None:
    email = _email()
    browser = env.browser()
    await browser.post("/auth/register", _registration(email))
    (message,) = await env.deliver()
    await env.sql(update(OneTimeToken).values(expires_at=text("now() - interval '1 second'")))
    response = await browser.post("/auth/verify-email", {"token": _token(message)})
    assert response.status_code == 400
    assert response.json()["code"] == "token_invalid"
    assert (await browser.post("/auth/verify-email", {"token": "x" * 43})).status_code == 400
    await browser.close()


async def test_change_password(env: Env) -> None:
    email = await _register_and_verify(env)
    browser = await _signed_in(env, email)
    other = await _signed_in(env, email)
    before = browser.client.cookies.get(SESSION)
    wrong = await browser.post(
        "/me/password", {"current_password": "not it at all", "new_password": NEW_PASSWORD}
    )
    assert wrong.status_code == 400
    assert wrong.json()["code"] == "current_password_incorrect"
    weak = await browser.post("/me/password", {"current_password": PASSWORD, "new_password": email})
    assert weak.status_code == 422
    ok = await browser.post(
        "/me/password", {"current_password": PASSWORD, "new_password": NEW_PASSWORD}
    )
    assert ok.status_code == 204
    assert browser.client.cookies.get(SESSION) != before  # rotated
    assert (await browser.get("/me")).status_code == 200
    assert (await other.get("/me")).status_code == 401
    assert any("changed" in m.subject for m in await env.deliver())
    unauthenticated = await env.browser().post(
        "/me/password", {"current_password": "a", "new_password": "b"}
    )
    assert unauthenticated.status_code == 401
    await browser.close()
    await other.close()


# --- Rate limiting -------------------------------------------------------------------------------
async def test_login_rate_limits_per_ip_and_per_account(env: Env) -> None:
    email = await _register_and_verify(env)
    attacker = env.browser(ip="203.0.113.99")
    codes = [
        (
            await attacker.post("/auth/login", {"email": email, "password": f"wrong guess {i:04d}"})
        ).status_code
        for i in range(6)
    ]
    assert codes[:5] == [401] * 5
    assert codes[5] == 429
    limited = await attacker.post("/auth/login", {"email": email, "password": PASSWORD})
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0

    # Distributed guessing from many addresses still hits the per-account failure limit.
    for i in range(5):
        await env.browser(ip=f"198.18.0.{i}").post(
            "/auth/login", {"email": email, "password": "wrong guess 9999"}
        )
    locked = await env.browser(ip="198.18.1.1").post(
        "/auth/login", {"email": email, "password": PASSWORD}
    )
    assert locked.status_code == 429  # even the right password waits out the window
    await attacker.close()


async def test_auth_fails_closed_when_rate_limiter_is_down(identity_db: str) -> None:
    app = create_app(_settings(identity_db, "redis://127.0.0.1:9/0"))
    browser = Browser(app, "203.0.113.30")
    response = await browser.post("/auth/login", {"email": _email(), "password": PASSWORD})
    assert response.status_code == 503
    assert response.json()["code"] == "rate_limiter_unavailable"
    await browser.close()
    await app.state.db_engine.dispose()
    await app.state.redis.aclose()


# --- Authorization -------------------------------------------------------------------------------
async def test_role_boundaries_are_enforced_server_side(env: Env) -> None:
    anonymous = env.browser()
    assert (await anonymous.get("/admin/session")).status_code == 401
    assert (await anonymous.get("/me")).status_code == 401
    email = await _register_and_verify(env)
    student = await _signed_in(env, email)
    denied = await student.get("/admin/session")
    assert denied.status_code == 403
    assert denied.json()["code"] == "permission_denied"

    user_id = (await env.sql(select(User.id).where(User.email == email))).scalar_one()
    reviewer = (await env.sql(select(Role.id).where(Role.code == "reviewer"))).scalar_one()
    await env.sql(insert(UserRole).values(user_id=user_id, role_id=reviewer))
    staff = await student.get("/admin/session")  # roles are re-read on every request
    assert staff.status_code == 200
    assert "admin.access" in staff.json()["permissions"]
    assert "content.publish" not in staff.json()["permissions"]
    await env.sql(delete(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == reviewer))
    assert (await student.get("/admin/session")).status_code == 403  # revocation is immediate
    await anonymous.close()
    await student.close()


# --- Outbox reliability -------------------------------------------------------------------------
async def test_outbox_retries_smtp_failures_and_then_delivers(env: Env) -> None:
    browser = env.browser()
    await browser.post("/auth/register", _registration(_email()))
    env.outbox.fail_next = 1
    assert await env.dispatcher.process_batch() == 1
    row = (await env.sql(select(OutboxMessage))).scalars().all()[-1]
    assert (row.status, row.attempts, row.last_error) == ("pending", 1, "SMTPServerDisconnected")
    assert row.next_attempt_at > row.updated_at  # backed off
    await env.sql(
        update(OutboxMessage)
        .where(OutboxMessage.id == row.id)
        .values(next_attempt_at=text("now()"))
    )
    (message,) = await env.deliver()
    row = (await env.sql(select(OutboxMessage).where(OutboxMessage.id == row.id))).scalar_one()
    assert row.status == "sent"
    assert row.payload == {}
    assert row.sent_at is not None
    assert (await browser.post("/auth/verify-email", {"token": _token(message)})).status_code == 204
    await browser.close()


async def test_outbox_survives_worker_crash_and_fences_stale_completion(env: Env) -> None:
    browser = env.browser()
    await browser.post("/auth/register", _registration(_email()))
    # Simulate a worker that claimed the row and crashed before finishing.
    await env.sql(
        text(
            "UPDATE outbox_messages SET attempts = attempts + 1, "
            "locked_until = now() + interval '5 minutes' WHERE status = 'pending'"
        )
    )
    assert await env.dispatcher.process_batch() == 0  # leased: not taken by another worker
    await env.sql(
        text(
            "UPDATE outbox_messages SET locked_until = now() - interval '1 second' "
            "WHERE status = 'pending'"
        )
    )
    (message,) = await env.deliver()  # lease expired: retried, link still valid
    assert (await browser.post("/auth/verify-email", {"token": _token(message)})).status_code == 204
    await browser.close()


async def test_outbox_redelivery_after_lost_completion_sends_same_valid_link(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SMTP accepted the email but the completion write was lost (database failure): the retry
    re-sends the same still-valid link with the same Message-ID, never a dead one."""
    browser = env.browser()
    await browser.post("/auth/register", _registration(_email()))
    original = env.dispatcher._write
    lost: list[str] = []

    async def lose_first_completion(statement: Any, params: dict[str, Any]) -> None:
        if "status" in params and not lost:
            lost.append("completion")  # the write never reaches the database
            return
        await original(statement, params)

    monkeypatch.setattr(env.dispatcher, "_write", lose_first_completion)
    assert await env.dispatcher.process_batch() == 1
    assert lost == ["completion"]
    assert len(env.outbox.sent) == 1
    row = (await env.sql(select(OutboxMessage))).scalar_one()
    assert row.status == "pending"
    assert row.locked_until is not None
    await env.sql(update(OutboxMessage).values(locked_until=text("now() - interval '1 second'")))
    (again,) = await env.deliver()
    first = env.outbox.sent[0]
    assert again.message_id == first.message_id
    assert _token(again) == _token(first)
    assert (await env.sql(select(OutboxMessage.status))).scalar_one() == "sent"
    assert (await browser.post("/auth/verify-email", {"token": _token(again)})).status_code == 204
    await browser.close()


async def test_outbox_skips_superseded_tokens_and_gives_up_after_max_attempts(env: Env) -> None:
    email = _email()
    browser = env.browser()
    await browser.post("/auth/register", _registration(email))
    await browser.post("/auth/verify-email/resend", {"email": email})
    delivered = await env.deliver()
    assert len(delivered) == 1  # the superseded first link was never sent
    statuses = sorted((await env.sql(select(OutboxMessage.status))).scalars().all())
    assert statuses == ["sent", "skipped"]

    await browser.post("/auth/password/forgot", {"email": email})
    env.outbox.fail_next = MAX_ATTEMPTS
    for _ in range(MAX_ATTEMPTS):
        await env.sql(
            update(OutboxMessage)
            .where(OutboxMessage.status == "pending")
            .values(next_attempt_at=text("now()"))
        )
        await env.dispatcher.process_batch()
    dead = (await env.sql(select(OutboxMessage).where(OutboxMessage.status == "dead"))).scalar_one()
    assert dead.attempts == MAX_ATTEMPTS
    assert dead.payload == {}
    await browser.close()


async def test_cleanup_removes_spent_tokens_and_old_sessions(env: Env) -> None:
    email = await _register_and_verify(env)
    browser = await _signed_in(env, email)
    await browser.post("/auth/logout")
    await env.sql(text("UPDATE one_time_tokens SET consumed_at = now() - interval '8 days'"))
    await env.sql(
        text(
            "UPDATE auth_sessions SET revoked_at = now() - interval '31 days' "
            "WHERE revoked_at IS NOT NULL"
        )
    )
    await env.dispatcher.cleanup()
    assert (await env.sql(select(OneTimeToken))).scalars().all() == []
    assert (
        await env.sql(select(AuthSession).where(AuthSession.revoked_at.is_not(None)))
    ).scalars().all() == []
    await browser.close()


async def test_staff_access_refused_while_two_factor_is_required(
    identity_db: str, redis_url: str
) -> None:
    """Production always requires staff 2FA; until it exists, the staff gate refuses access."""
    settings = _settings(identity_db, redis_url, staff_mfa_required=True)
    app = create_app(settings)
    sender = MemoryEmailSender()
    env = Env(app, settings, sender, Dispatcher(settings, app.state.db_session_factory, sender))
    email = await _register_and_verify(env)
    user_id = (await env.sql(select(User.id).where(User.email == email))).scalar_one()
    admin = (await env.sql(select(Role.id).where(Role.code == "admin"))).scalar_one()
    await env.sql(insert(UserRole).values(user_id=user_id, role_id=admin))
    browser = await _signed_in(env, email)
    response = await browser.get("/admin/session")
    assert response.status_code == 403
    assert response.json()["code"] == "mfa_required"
    await browser.close()
    await app.state.db_engine.dispose()
    await app.state.redis.aclose()
