"""Secrets, opaque tokens and their hashes (SECURITY_GUIDELINES.md §2).

- Session tokens: 256-bit random, URL-safe; the database stores SHA-256 hashes only.
- One-time tokens (verify email, reset password) are derived, not stored:
  `raw = HMAC(one_time_key, purpose ‖ 0x00 ‖ salt)`. The request transaction stores the token's
  SHA-256 hash (one_time_tokens) and the random salt (outbox payload) atomically. The outbox
  worker re-derives the exact link from the salt after a crash or retry, so an email can never
  carry a token whose database row failed to commit. A database leak without AUTH_SECRET_KEY
  yields neither raw tokens nor the ability to derive them (equivalent protection to an
  encrypted payload, using only the standard library).
"""

import base64
import hashlib
import hmac
import ipaddress
import secrets
from dataclasses import dataclass

import structlog

from app.core.config import Settings

log = structlog.get_logger("app.identity")

SESSION_TOKEN_BYTES = 32
RAW_TOKEN_LENGTH = 43  # URL-safe base64 of 32 bytes, without padding


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass(frozen=True)
class AuthKeys:
    """Purpose-separated keys derived from AUTH_SECRET_KEY."""

    csrf: bytes
    one_time_token: bytes
    mfa_secret: bytes  # AES-256-GCM key for stored TOTP secrets
    mfa_recovery: bytes  # HMAC key for recovery-code hashes

    @classmethod
    def from_secret(cls, secret: bytes) -> AuthKeys:
        def derive(label: str) -> bytes:
            return hmac.new(secret, f"ielts-master/{label}".encode(), hashlib.sha256).digest()

        return cls(
            csrf=derive("csrf/v1"),
            one_time_token=derive("one-time-token/v1"),
            mfa_secret=derive("mfa-secret/v1"),
            mfa_recovery=derive("mfa-recovery/v1"),
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> AuthKeys:
        if settings.auth_secret_key is not None:
            return cls.from_secret(settings.auth_secret_key.get_secret_value().encode())
        if not settings.is_dev_like:  # also enforced by Settings validation
            raise RuntimeError("AUTH_SECRET_KEY is required outside local/ci")
        log.warning("auth.ephemeral_secret", detail="AUTH_SECRET_KEY unset: per-process key")
        return cls.from_secret(secrets.token_bytes(32))


def new_session_token() -> str:
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def hash_token(raw: str) -> bytes:
    return hashlib.sha256(raw.encode("utf-8")).digest()


def new_salt() -> bytes:
    return secrets.token_bytes(32)


def derive_one_time_token(key: bytes, purpose: str, salt: bytes) -> str:
    digest = hmac.new(key, purpose.encode() + b"\x00" + salt, hashlib.sha256).digest()
    return _b64(digest)


def looks_like_token(value: str) -> bool:
    """Cheap shape check before any database work."""
    if len(value) != RAW_TOKEN_LENGTH:
        return False
    try:
        return len(b64_decode(value)) == 32
    except ValueError:
        return False


def ip_prefix(ip: str | None) -> str | None:
    """Truncate to /24 (IPv4) or /48 (IPv6): enough for abuse analysis, not a precise identifier."""
    if not ip:
        return None
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return None
    bits = 24 if address.version == 4 else 48
    return str(ipaddress.ip_network(f"{address}/{bits}", strict=False))


def subject_digest(value: str) -> str:
    """Stable, non-reversible key fragment for rate limiting (no raw emails or IPs in Redis)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
