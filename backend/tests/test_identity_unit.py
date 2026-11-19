"""Identity building blocks without a database: policy, tokens, CSRF signatures, config rules."""

from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.modules.identity.csrf import issue_token, token_is_valid
from app.modules.identity.passwords import PasswordService, common_passwords, policy_problem
from app.modules.identity.schemas import RegisterRequest
from app.modules.identity.tokens import (
    AuthKeys,
    derive_one_time_token,
    ip_prefix,
    looks_like_token,
    new_salt,
)

DB = "postgresql://t:t@127.0.0.1:9/t"
REDIS = "redis://127.0.0.1:9/0"
KEY = "unit-test-secret-key-0123456789abcdef"


def _settings(**overrides: Any) -> Settings:
    return Settings(database_url=DB, redis_url=REDIS, **overrides)


@pytest.mark.parametrize(
    ("password", "problem"),
    [
        ("short", "at least 10"),
        ("x" * 129, "at most 128"),
        ("password1234", "too common"),
        ("QWERTYUIOP", "too common"),  # case-insensitive
        ("amina.rahman2026", "email"),
        ("my ieltsmaster pass", "site name"),
        ("correct horse battery staple", None),
    ],
)
def test_password_policy(password: str, problem: str | None) -> None:
    result = policy_problem(password, email="amina.rahman@example.test")
    assert (result is None) if problem is None else (problem in (result or ""))


def test_blocklist_loaded_and_filtered_to_policy_lengths() -> None:
    words = common_passwords()
    assert len(words) > 100_000
    assert all(10 <= len(w) <= 128 for w in list(words)[:1000])


async def test_password_hashing_normalises_and_rejects_wrong_passwords() -> None:
    service = PasswordService(memory_kib=1024, iterations=1, concurrency=2)
    hashed = await service.hash("ｃａｆé password 10")  # full-width input (NFKC)
    assert hashed.startswith("$argon2id$")
    assert await service.verify(hashed, "café password 10")
    assert not await service.verify(hashed, "cafe password 10")
    assert not await service.verify(None, "anything at all")  # decoy path
    assert service.needs_rehash(hashed) is False
    stronger = PasswordService(memory_kib=2048, iterations=2, concurrency=1)
    assert stronger.needs_rehash(hashed) is True


def test_one_time_tokens_are_deterministic_per_salt_and_purpose() -> None:
    keys = AuthKeys.from_secret(KEY.encode())
    salt = new_salt()
    token = derive_one_time_token(keys.one_time_token, "verify_email", salt)
    assert looks_like_token(token)
    assert token == derive_one_time_token(keys.one_time_token, "verify_email", salt)
    assert token != derive_one_time_token(keys.one_time_token, "reset_password", salt)
    other = AuthKeys.from_secret(b"another-secret-key-0123456789abcdef")
    assert token != derive_one_time_token(other.one_time_token, "verify_email", salt)
    assert keys.csrf != keys.one_time_token  # purpose-separated keys
    assert not looks_like_token("x" * 42)
    assert not looks_like_token("!" * 43)


def test_csrf_token_is_bound_to_the_session() -> None:
    keys = AuthKeys.from_secret(KEY.encode())
    anonymous = issue_token(keys, None)
    assert token_is_valid(keys, None, anonymous)
    assert not token_is_valid(keys, "some-session", anonymous)
    bound = issue_token(keys, "some-session")
    assert token_is_valid(keys, "some-session", bound)
    assert not token_is_valid(keys, "other-session", bound)
    assert not token_is_valid(keys, "some-session", bound[:-1] + ("0" if bound[-1] != "0" else "1"))
    assert not token_is_valid(keys, None, "garbage")


def test_ip_prefix_truncates() -> None:
    assert ip_prefix("203.0.113.77") == "203.0.113.0/24"
    assert ip_prefix("2001:db8:abcd:12::1") == "2001:db8:abcd::/48"
    assert ip_prefix("not-an-ip") is None
    assert ip_prefix(None) is None


def test_email_and_name_validation() -> None:
    ok = RegisterRequest(
        full_name="  Amina   Rahman ",
        email="Amina@Bücher.example",
        password="x",
        accept_terms=True,
        age_confirmation=True,
    )
    assert ok.full_name == "Amina Rahman"
    assert ok.email == "Amina@xn--bcher-kva.example"
    for bad in ("plain", "a@b", "a..b@example.test", "a@exa mple.test", "a@-x.test"):
        with pytest.raises(ValidationError):
            RegisterRequest(
                full_name="A", email=bad, password="x", accept_terms=True, age_confirmation=True
            )
    with pytest.raises(ValidationError):
        RegisterRequest(
            full_name="A\u0000B",
            email="a@example.test",
            password="x",
            accept_terms=True,
            age_confirmation=True,
        )


# --- Configuration rules (D-13 / D-17 safety) -----------------------------------------------------
def test_local_defaults_use_marked_placeholders() -> None:
    s = _settings(app_env="local")
    assert s.registration_open
    assert s.uses_policy_placeholders
    assert s.terms_version_effective == "dev-placeholder"
    assert s.cookie_secure_effective is False
    assert s.staff_mfa_required_effective is False


def test_staging_and_production_close_registration_by_default() -> None:
    for env in ("staging", "production"):
        s = _settings(app_env=env, auth_secret_key=KEY, public_app_url="https://app.example.test")
        assert s.registration_open is False
        assert s.cookie_secure_effective is True
        assert s.staff_mfa_required_effective is True


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({}, "AUTH_SECRET_KEY is required"),
        ({"auth_secret_key": "too-short"}, "at least 32"),
        ({"auth_secret_key": KEY, "registration_enabled": True}, "approved age policy"),
        (
            {
                "auth_secret_key": KEY,
                "registration_enabled": True,
                "registration_minimum_age": 18,
                "legal_terms_version": "dev-placeholder",
                "legal_privacy_version": "2026-01",
            },
            "placeholders are not allowed",
        ),
        ({"auth_secret_key": KEY, "session_cookie_secure": False}, "SESSION_COOKIE_SECURE"),
        ({"auth_secret_key": KEY, "staff_mfa_required": False}, "STAFF_MFA_REQUIRED"),
        ({"auth_secret_key": KEY, "public_app_url": "http://app.example.test"}, "https"),
        ({"auth_secret_key": KEY, "smtp_security": "none"}, "SMTP_SECURITY"),
        ({"auth_secret_key": KEY, "password_hash_memory_kib": 1024}, "OWASP"),
    ],
)
def test_production_refuses_unsafe_configuration(overrides: dict[str, Any], message: str) -> None:
    base: dict[str, Any] = {"app_env": "production", "public_app_url": "https://app.example.test"}
    with pytest.raises(ValidationError, match=message):
        _settings(**{**base, **overrides})


def test_production_registration_requires_and_accepts_approved_values() -> None:
    s = _settings(
        app_env="production",
        auth_secret_key=KEY,
        public_app_url="https://app.example.test",
        registration_enabled=True,
        registration_minimum_age=18,
        legal_terms_version="2026-12-01",
        legal_privacy_version="2026-12-01",
    )
    assert s.registration_open
    assert not s.uses_policy_placeholders


def test_totp_matches_rfc6238_and_rejects_bad_codes() -> None:
    from app.modules.identity import mfa

    secret = b"12345678901234567890"  # RFC 6238 Appendix B (SHA-1)
    assert mfa.hotp(secret, 1) == "287082"  # T = 59 s, last 6 of 94287082
    assert mfa.match_step(secret, "287082", now=59) == 1
    assert mfa.match_step(secret, "287 082", now=59 + 30) == 1  # previous step still accepted
    assert mfa.match_step(secret, "287082", now=59 + 90) is None  # outside the window
    assert mfa.match_step(secret, "28708", now=59) is None
    assert mfa.match_step(secret, "abcdef", now=59) is None
    uri = mfa.otpauth_uri(secret, "a@b.test")
    assert uri.startswith("otpauth://totp/IELTS%20MASTER%3Aa%40b.test?secret=GEZDGNBV")
