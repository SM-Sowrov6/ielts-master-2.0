"""Super Admin foundation against real PostgreSQL + Redis: provisioning, the staff gate and the
admin console API. Requires TEST_DATABASE_ADMIN_URL and TEST_REDIS_URL.

Shared fixtures and the same-origin `Browser` come from the authentication suite.
"""

import argparse
import hashlib
import importlib.util
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from redis.asyncio import Redis
from sqlalchemy import func, select, text, update
from sqlalchemy.engine import make_url
from test_identity_integration import (
    ALEMBIC_INI,
    CSRF,
    PASSWORD,
    SESSION,
    Env,
    _register_and_verify,
    _settings,
    _signed_in,
)

from app.core.email import MemoryEmailSender
from app.main import create_app
from app.modules.audit.models import AuditLog
from app.modules.identity.models import AuthSession, Role, User, UserRole
from app.modules.identity.passwords import PasswordService
from app.modules.identity.provisioning import (
    ProvisioningError,
    create_staff_account,
    grant_role,
    list_staff,
    revoke_role,
)
from app.workers.outbox import Dispatcher

pytestmark = pytest.mark.integration

ADMIN_PASSWORD = "operator chosen passphrase 7731"
ADMIN_ENDPOINTS = ("/admin/session", "/admin/overview/users", "/admin/overview/content")
AUDIT = "/admin/audit-logs"
FAST_HASHER = PasswordService(memory_kib=1024, iterations=1, concurrency=1)
ADMIN_CLI = Path(__file__).resolve().parents[2] / "scripts" / "admin_cli.py"


def load_admin_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location("admin_cli", ADMIN_CLI)
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def admin_db(test_database_url: str) -> str:
    """The shared test database at the latest migration (as in the authentication suite)."""
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["configure_logger"] = False
    cfg.attributes["database_url"] = test_database_url
    command.upgrade(cfg, "head")
    return test_database_url


@pytest.fixture
async def admin_redis(test_redis_url: str) -> str:
    """Redis database 15 is reserved for tests and flushed, so rate limits start fresh."""
    url = make_url(test_redis_url).set(database="15").render_as_string(hide_password=False)
    client = Redis.from_url(url)
    await client.flushdb()
    await client.aclose()
    return url


@pytest.fixture
async def env(admin_db: str, admin_redis: str) -> AsyncIterator[Env]:
    settings = _settings(admin_db, admin_redis)
    app = create_app(settings)
    sender = MemoryEmailSender()
    async with app.state.db_session_factory() as db, db.begin():
        await db.execute(text("DELETE FROM outbox_messages"))
    yield Env(app, settings, sender, Dispatcher(settings, app.state.db_session_factory, sender))
    await app.state.db_engine.dispose()
    await app.state.redis.aclose()


def _admin_email() -> str:
    return f"admin-{uuid.uuid4().hex[:10]}@example.test"


async def _db_call(env: Env, fn: Any, **kwargs: Any) -> Any:
    async with env.app.state.db_session_factory() as db, db.begin():
        return await fn(db, **kwargs)


async def _create_super_admin(env: Env, email: str | None = None) -> str:
    email = email or _admin_email()
    change = await _db_call(
        env,
        create_staff_account,
        passwords=FAST_HASHER,
        email=email,
        full_name="Platform Owner",
        password=ADMIN_PASSWORD,
        role="super_admin",
    )
    assert change.created
    assert change.changed
    return email


async def _grant(env: Env, email: str, role: str) -> None:
    await _db_call(env, grant_role, email=email, role=role)


def _all_admin_paths() -> tuple[str, ...]:
    return (*ADMIN_ENDPOINTS, AUDIT)


# --- Provisioning --------------------------------------------------------------------------------
async def test_initial_super_admin_signs_in_through_the_normal_login(env: Env) -> None:
    email = await _create_super_admin(env)
    user = (await env.sql(select(User).where(User.email == email))).scalar_one()
    assert user.status == "active"
    assert user.email_verified_at is not None
    assert ADMIN_PASSWORD not in user.password_hash
    assert user.password_hash.startswith("$argon2id$")

    browser = await _signed_in(env, email, ADMIN_PASSWORD)
    me = (await browser.get("/me")).json()
    assert me["roles"] == ["super_admin"]
    assert {"admin.access", "roles.manage", "system.configure"} <= set(me["permissions"])
    for path in _all_admin_paths():
        response = await browser.get(path)
        assert response.status_code == 200, (path, response.text)
        assert response.headers["cache-control"] == "no-store"

    actions = (
        (await env.sql(select(AuditLog.action).where(AuditLog.entity_id == user.id)))
        .scalars()
        .all()
    )
    assert {"identity.user.provisioned", "identity.role.granted"} <= set(actions)
    provisioned = (
        await env.sql(
            select(AuditLog).where(
                AuditLog.entity_id == user.id, AuditLog.action == "identity.role.granted"
            )
        )
    ).scalar_one()
    assert provisioned.actor_user_id is None
    assert provisioned.changes == {"role": "super_admin", "via": "admin_cli"}
    await browser.close()


async def test_repeated_provisioning_is_idempotent_and_never_resets_the_password(
    env: Env,
) -> None:
    email = await _create_super_admin(env)
    user_id = (await env.sql(select(User.id).where(User.email == email))).scalar_one()
    audit_before = (
        await env.sql(select(func.count()).where(AuditLog.entity_id == user_id))
    ).scalar_one()
    again = await _db_call(
        env,
        create_staff_account,
        passwords=FAST_HASHER,
        email=email.upper(),  # same account, differently typed
        full_name="Someone Else",
        password="a different passphrase 0000",
        role="super_admin",
    )
    assert not again.changed
    assert not again.created
    granted = await _db_call(env, grant_role, email=email, role="super_admin")
    assert not granted.changed
    roles = (await env.sql(select(func.count()).where(UserRole.user_id == user_id))).scalar_one()
    assert roles == 1
    audit_after = (
        await env.sql(select(func.count()).where(AuditLog.entity_id == user_id))
    ).scalar_one()
    assert audit_after == audit_before
    browser = await _signed_in(env, email, ADMIN_PASSWORD)  # original password still works
    await browser.close()


async def test_provisioning_refuses_unsafe_requests(env: Env) -> None:
    with pytest.raises(ProvisioningError, match="not a staff role"):
        await _db_call(env, grant_role, email=_admin_email(), role="student")
    with pytest.raises(ProvisioningError, match="No account"):
        await _db_call(env, grant_role, email=_admin_email(), role="admin")
    with pytest.raises(ProvisioningError, match="Password rejected"):
        await _db_call(
            env,
            create_staff_account,
            passwords=FAST_HASHER,
            email=_admin_email(),
            full_name="Weak Password",
            password="password1",
            role="admin",
        )
    with pytest.raises(ProvisioningError, match="valid email"):
        await _db_call(env, grant_role, email="not-an-email", role="admin")

    # A registered but unverified account cannot be elevated: whoever registered it may not own
    # the mailbox.
    pending = _admin_email()
    browser = env.browser()
    body = {
        "full_name": "Not Verified",
        "email": pending,
        "password": PASSWORD,
        "accept_terms": True,
        "age_confirmation": True,
    }
    assert (await browser.post("/auth/register", body)).status_code == 202
    await env.deliver()  # the verification email is never opened
    with pytest.raises(ProvisioningError, match="'pending'"):
        await _db_call(env, grant_role, email=pending, role="super_admin")
    # Suspended accounts neither.
    suspended = await _register_and_verify(env)
    await env.sql(update(User).where(User.email == suspended).values(status="suspended"))
    with pytest.raises(ProvisioningError, match="'suspended'"):
        await _db_call(env, grant_role, email=suspended, role="admin")
    await browser.close()


async def test_promotion_revokes_existing_sessions(env: Env) -> None:
    email = await _register_and_verify(env)
    before = await _signed_in(env, email)
    assert (await before.get("/admin/session")).status_code == 403
    change = await _db_call(env, grant_role, email=email, role="admin")
    assert change.changed
    assert change.sessions_revoked == 1
    assert (await before.get("/admin/session")).status_code == 401  # must sign in again
    after = await _signed_in(env, email)
    assert (await after.get("/admin/session")).status_code == 200
    await before.close()
    await after.close()


async def test_revoking_a_role_is_immediate_and_protects_the_last_super_admin(env: Env) -> None:
    # Start from a clean slate of super admins so "last one" is deterministic.
    await env.sql(
        text(
            "DELETE FROM user_roles"
            " WHERE role_id = (SELECT id FROM roles WHERE code = 'super_admin')"
        )
    )
    owner = await _create_super_admin(env)
    browser = await _signed_in(env, owner, ADMIN_PASSWORD)
    with pytest.raises(ProvisioningError, match="last active super admin"):
        await _db_call(env, revoke_role, email=owner, role="super_admin")
    second = await _create_super_admin(env)
    change = await _db_call(env, revoke_role, email=owner, role="super_admin")
    assert change.changed
    assert change.sessions_revoked == 1
    assert (await browser.get("/admin/session")).status_code == 401
    again = await _signed_in(env, owner, ADMIN_PASSWORD)
    denied = await again.get("/admin/overview/users")
    assert denied.status_code == 403  # now an account without any role
    assert not (await _db_call(env, revoke_role, email=owner, role="super_admin")).changed
    staff = {m.email: m.roles for m in await _db_call(env, list_staff)}
    assert staff[second] == ("super_admin",)
    assert owner not in staff
    await browser.close()
    await again.close()


async def test_admin_cli_provisions_from_an_environment_variable(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin_cli = load_admin_cli()
    email = _admin_email()
    monkeypatch.setenv("TEST_INITIAL_ADMIN_PASSWORD", ADMIN_PASSWORD)
    parser = admin_cli.build_parser()
    args = parser.parse_args(
        [
            "create-staff",
            email,
            "--full-name",
            "CLI Owner",
            "--password-env",
            "TEST_INITIAL_ADMIN_PASSWORD",
        ]
    )
    output = await admin_cli.execute(args, env.settings)
    assert "Created active account" in output
    assert ADMIN_PASSWORD not in output
    rerun = await admin_cli.execute(args, env.settings)
    assert rerun.startswith("No change")
    listing = await admin_cli.execute(argparse.Namespace(command="list-staff"), env.settings)
    assert email in listing
    assert "super_admin" in listing
    browser = await _signed_in(env, email, ADMIN_PASSWORD)
    assert (await browser.get("/admin/session")).status_code == 200
    await browser.close()


# --- Authorization of the admin API --------------------------------------------------------------
async def test_anonymous_and_students_are_refused_everywhere(env: Env) -> None:
    anonymous = env.browser()
    for path in _all_admin_paths():
        response = await anonymous.get(path)
        assert response.status_code == 401, path
        assert response.json()["code"] == "not_authenticated"
    student = await _signed_in(env, await _register_and_verify(env))
    for path in _all_admin_paths():
        response = await student.get(path)
        assert response.status_code == 403, path
        assert response.json()["code"] == "permission_denied"
        assert "total" not in response.text
        assert "items" not in response.text
    await anonymous.close()
    await student.close()


async def test_client_supplied_role_data_grants_nothing(env: Env) -> None:
    student = await _signed_in(env, await _register_and_verify(env))
    forged = {"X-Role": "super_admin", "X-User-Roles": "super_admin", "X-Permissions": "*"}
    for path in _all_admin_paths():
        response = await student.client.get(f"/api/v1{path}", headers=forged)
        assert response.status_code == 403, path
    # A forged session cookie is not a session.
    student.client.cookies.set(SESSION, "forged-" + "a" * 36)
    assert (await student.get("/admin/session")).status_code == 401
    await student.close()


async def test_no_http_route_can_grant_roles(env: Env) -> None:
    schema = env.app.openapi()
    for path in schema["paths"]:
        assert "role" not in path.lower(), path  # roles change only through scripts/admin_cli.py
    owner = await _signed_in(env, await _create_super_admin(env), ADMIN_PASSWORD)
    student_email = await _register_and_verify(env)
    student_id = (await env.sql(select(User.id).where(User.email == student_email))).scalar_one()
    for path in (f"/admin/users/{student_id}/roles", "/admin/roles", "/admin/provision"):
        response = await owner.post(path, {"role": "super_admin"})
        assert response.status_code in (404, 405), path
    student = await _signed_in(env, student_email)
    assert (await student.get("/admin/session")).status_code == 403
    await owner.close()
    await student.close()


async def test_permissions_follow_least_privilege(env: Env) -> None:
    reviewer_email = await _register_and_verify(env)
    await _grant(env, reviewer_email, "reviewer")
    reviewer = await _signed_in(env, reviewer_email)
    assert (await reviewer.get("/admin/session")).status_code == 200
    assert (await reviewer.get("/admin/overview/content")).status_code == 200
    assert (await reviewer.get("/admin/overview/users")).status_code == 403
    assert (await reviewer.get(AUDIT)).status_code == 403

    manager_email = await _register_and_verify(env)
    await _grant(env, manager_email, "content_manager")
    manager = await _signed_in(env, manager_email)
    assert (await manager.get("/admin/overview/content")).status_code == 200
    assert (await manager.get("/admin/overview/users")).status_code == 403

    admin_email = await _register_and_verify(env)
    await _grant(env, admin_email, "admin")
    admin = await _signed_in(env, admin_email)
    for path in _all_admin_paths():
        assert (await admin.get(path)).status_code == 200, path
    for b in (reviewer, manager, admin):
        await b.close()


async def test_dashboard_data_is_real(env: Env) -> None:
    owner_email = await _create_super_admin(env)
    owner = await _signed_in(env, owner_email, ADMIN_PASSWORD)
    users = (await owner.get("/admin/overview/users")).json()
    expected_students = (
        await env.sql(
            select(func.count())
            .select_from(UserRole)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.code == "student")
        )
    ).scalar_one()
    total = (await env.sql(select(func.count()).select_from(User))).scalar_one()
    assert users["students"] == expected_students
    assert users["total"] == total == sum(users["by_status"].values())
    assert users["staff_by_role"]["super_admin"] >= 1
    assert set(users["staff_by_role"]) == {"super_admin", "admin", "content_manager", "reviewer"}

    content = (await owner.get("/admin/overview/content")).json()
    books = (await env.sql(text("SELECT count(*) FROM books WHERE deleted_at IS NULL"))).scalar()
    assert content["books"] == books
    assert set(content["versions_by_status"]) == {"draft", "in_review", "published", "archived"}
    assert set(content["published_modules"]) == {"listening", "reading", "writing", "speaking"}

    page = (await owner.get(f"{AUDIT}?limit=5")).json()
    assert 1 <= len(page["items"]) <= 5
    newest = page["items"][0]
    assert newest["action"] == "identity.login.succeeded"
    assert newest["actor"]["name"] == "Platform Owner"
    assert "ip" not in newest
    assert "changes" not in newest
    stamps = [item["created_at"] for item in page["items"]]
    assert stamps == sorted(stamps, reverse=True)
    assert (await owner.get(f"{AUDIT}?limit=500")).status_code == 422
    await owner.close()


# --- Sessions ------------------------------------------------------------------------------------
async def test_expired_revoked_and_signed_out_admin_sessions_are_refused(env: Env) -> None:
    email = await _create_super_admin(env)
    idle = await _signed_in(env, email, ADMIN_PASSWORD)
    token_hash = hashlib.sha256(idle.client.cookies[SESSION].encode()).digest()
    await env.sql(
        update(AuthSession)
        .where(AuthSession.token_hash == token_hash)
        .values(idle_expires_at=text("now() - interval '1 second'"))
    )
    assert (await idle.get("/admin/overview/users")).status_code == 401

    absolute = await _signed_in(env, email, ADMIN_PASSWORD)
    token_hash = hashlib.sha256(absolute.client.cookies[SESSION].encode()).digest()
    await env.sql(
        update(AuthSession)
        .where(AuthSession.token_hash == token_hash)
        .values(absolute_expires_at=text("now() - interval '1 second'"))
    )
    assert (await absolute.get("/admin/session")).status_code == 401

    browser = await _signed_in(env, email, ADMIN_PASSWORD)
    other_device = await _signed_in(env, email, ADMIN_PASSWORD)
    assert (await browser.post("/auth/logout")).status_code == 204
    assert (await browser.get("/admin/session")).status_code == 401
    assert (await other_device.get("/admin/session")).status_code == 200
    assert (await other_device.post("/auth/logout-all")).status_code == 204
    assert (await other_device.get("/admin/session")).status_code == 401

    suspended = await _signed_in(env, email, ADMIN_PASSWORD)
    await env.sql(update(User).where(User.email == email).values(status="suspended"))
    assert (await suspended.get("/admin/session")).status_code == 401
    for b in (idle, absolute, browser, other_device, suspended):
        await b.close()


async def test_admin_sign_out_requires_a_valid_csrf_token(env: Env) -> None:
    email = await _create_super_admin(env)
    browser = await _signed_in(env, email, ADMIN_PASSWORD)
    missing = await browser.client.post("/api/v1/auth/logout")
    assert missing.status_code == 403
    assert missing.json()["code"] == "csrf_failed"
    cross_site = await browser.client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": browser.client.cookies[CSRF], "Origin": "https://evil.example"},
    )
    assert cross_site.status_code == 403
    unsafe_admin = await browser.client.post("/api/v1/admin/overview/users")
    assert unsafe_admin.status_code == 403
    assert unsafe_admin.json()["code"] == "csrf_failed"
    assert (await browser.get("/admin/session")).status_code == 200  # still signed in
    await browser.close()


async def test_admin_api_refused_while_staff_two_factor_is_required(
    admin_db: str, admin_redis: str
) -> None:
    settings = _settings(admin_db, admin_redis, staff_mfa_required=True)
    app = create_app(settings)
    sender = MemoryEmailSender()
    mfa_env = Env(app, settings, sender, Dispatcher(settings, app.state.db_session_factory, sender))
    email = await _create_super_admin(mfa_env)
    browser = await _signed_in(mfa_env, email, ADMIN_PASSWORD)
    for path in _all_admin_paths():
        response = await browser.get(path)
        assert response.status_code == 403, path
        assert response.json()["code"] == "mfa_required"
    await browser.close()
    await app.state.db_engine.dispose()
    await app.state.redis.aclose()
