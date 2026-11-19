"""Staff two-factor authentication: TOTP (RFC 6238) with single-use recovery codes.

Flow (SECURITY_GUIDELINES.md §2): a staff member signs in with a password, then the staff gate
(`require_staff`) answers 403 `mfa_required` until the session is upgraded here.

- `begin_setup`: creates (or replaces) an UNCONFIRMED factor and returns the secret once, as a
  base32 key and an `otpauth://` URI for the QR code. Refused when a confirmed factor exists.
- `confirm_setup`: proves the authenticator works, confirms the factor, issues 10 recovery codes
  (shown once) and upgrades the session.
- `verify`: a TOTP code or a recovery code upgrades the session.

Upgrading = revoking the current session and issuing a new one with `mfa_verified_at` set (no
session fixation across the privilege change). Secrets are encrypted with AES-256-GCM under a key
derived from AUTH_SECRET_KEY (rotating that key therefore requires staff to enrol again); recovery
codes are stored as HMAC-SHA256 hashes. A TOTP time step is accepted at most once (replay guard).
Attempts are rate-limited per user, and every outcome is audited.
"""

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote, urlencode

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit import api as audit
from app.modules.identity import ratelimit
from app.modules.identity.errors import MfaCodeInvalidError, MfaStateError
from app.modules.identity.models import AuthSession, UserMfaFactor, UserMfaRecoveryCode
from app.modules.identity.service import AuthRuntime, ClientMeta
from app.modules.identity.sessions import CurrentUser, create_session, revoke_session
from app.modules.identity.tokens import AuthKeys
from app.shared.ids import new_id

ISSUER = "IELTS MASTER"
DIGITS = 6
STEP_SECONDS = 30
WINDOW = 1  # accept the previous and next step too (clock drift)
RECOVERY_CODES = 10


# --- TOTP ----------------------------------------------------------------------------------------
def new_secret() -> bytes:
    return secrets.token_bytes(20)  # 160 bits (RFC 4226 recommendation)


def base32(secret: bytes) -> str:
    return base64.b32encode(secret).decode().rstrip("=")


def hotp(secret: bytes, counter: int) -> str:
    digest = hmac.new(secret, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP_SECONDS)


def match_step(secret: bytes, code: str, *, now: float | None = None) -> int | None:
    """The time step `code` belongs to (within ±WINDOW), or None."""
    code = code.strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    step = current_step(now)
    for candidate in range(step - WINDOW, step + WINDOW + 1):
        if hmac.compare_digest(hotp(secret, candidate), code):
            return candidate
    return None


def otpauth_uri(secret: bytes, account: str) -> str:
    label = quote(f"{ISSUER}:{account}")
    query = urlencode(
        {"secret": base32(secret), "issuer": ISSUER, "digits": DIGITS, "period": STEP_SECONDS}
    )
    return f"otpauth://totp/{label}?{query}"


# --- Storage protection --------------------------------------------------------------------------
def _seal(keys: AuthKeys, user_id: uuid.UUID, secret: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(keys.mfa_secret).encrypt(nonce, secret, user_id.bytes)


def _open(keys: AuthKeys, user_id: uuid.UUID, blob: bytes) -> bytes:
    return AESGCM(keys.mfa_secret).decrypt(blob[:12], blob[12:], user_id.bytes)


def _recovery_hash(keys: AuthKeys, code: str) -> bytes:
    normalized = code.strip().replace("-", "").replace(" ", "").lower()
    return hmac.new(keys.mfa_recovery, normalized.encode(), hashlib.sha256).digest()


def _new_recovery_code() -> str:
    raw = secrets.token_hex(5)  # 40 bits each, single use
    return f"{raw[:5]}-{raw[5:]}"


# --- Service -------------------------------------------------------------------------------------
@dataclass(frozen=True)
class MfaStatus:
    enrolled: bool
    verified: bool
    required: bool
    recovery_codes_left: int


@dataclass(frozen=True)
class SetupInfo:
    secret: str
    otpauth_uri: str


async def status(db: AsyncSession, user: CurrentUser, *, required: bool) -> MfaStatus:
    async with db.begin():
        factor = await db.get(UserMfaFactor, user.id)
        left = len(
            (
                await db.scalars(
                    select(UserMfaRecoveryCode.id).where(
                        UserMfaRecoveryCode.user_id == user.id,
                        UserMfaRecoveryCode.used_at.is_(None),
                    )
                )
            ).all()
        )
    return MfaStatus(
        enrolled=factor is not None and factor.confirmed_at is not None,
        verified=user.mfa_verified,
        required=required,
        recovery_codes_left=left,
    )


async def begin_setup(
    db: AsyncSession, rt: AuthRuntime, meta: ClientMeta, user: CurrentUser
) -> SetupInfo:
    keys = rt.keys
    secret = new_secret()
    async with db.begin():
        factor = await db.get(UserMfaFactor, user.id, with_for_update=True)
        if factor is not None and factor.confirmed_at is not None:
            raise MfaStateError
        if factor is None:
            db.add(UserMfaFactor(user_id=user.id, secret_ciphertext=_seal(keys, user.id, secret)))
        else:
            factor.secret_ciphertext = _seal(keys, user.id, secret)
            factor.last_used_step = None
        await _audit(db, meta, user, "identity.mfa.setup_started")
    return SetupInfo(secret=base32(secret), otpauth_uri=otpauth_uri(secret, user.email))


async def confirm_setup(
    db: AsyncSession,
    rt: AuthRuntime,
    meta: ClientMeta,
    user: CurrentUser,
    code: str,
) -> tuple[str, list[str]]:
    """Returns (new session token, recovery codes)."""
    keys, limiter = rt.keys, rt.limiter
    await limiter.enforce(ratelimit.MFA_USER, str(user.id))
    codes = [_new_recovery_code() for _ in range(RECOVERY_CODES)]
    async with db.begin():
        factor = await db.get(UserMfaFactor, user.id, with_for_update=True)
        if factor is None or factor.confirmed_at is not None:
            raise MfaStateError
        step = match_step(_open(keys, user.id, factor.secret_ciphertext), code)
        if step is None:
            await _audit(db, meta, user, "identity.mfa.setup_failed")
        else:
            factor.confirmed_at = datetime.now(UTC)
            factor.last_used_step = step
            await db.execute(
                delete(UserMfaRecoveryCode).where(UserMfaRecoveryCode.user_id == user.id)
            )
            db.add_all(
                UserMfaRecoveryCode(id=new_id(), user_id=user.id, code_hash=_recovery_hash(keys, c))
                for c in codes
            )
            await _audit(db, meta, user, "identity.mfa.enrolled")
            token = await _upgrade_session(db, rt, meta, user)
    if step is None:
        raise MfaCodeInvalidError
    await limiter.reset(ratelimit.MFA_USER, str(user.id))
    return token, codes


async def verify(
    db: AsyncSession,
    rt: AuthRuntime,
    meta: ClientMeta,
    user: CurrentUser,
    code: str,
) -> str:
    """A TOTP code or a recovery code; returns the new (verified) session token."""
    keys, limiter = rt.keys, rt.limiter
    await limiter.enforce(ratelimit.MFA_USER, str(user.id))
    token: str | None = None
    async with db.begin():
        factor = await db.get(UserMfaFactor, user.id, with_for_update=True)
        if factor is None or factor.confirmed_at is None:
            raise MfaStateError
        method = "totp"
        step = match_step(_open(keys, user.id, factor.secret_ciphertext), code)
        ok = step is not None and (factor.last_used_step is None or step > factor.last_used_step)
        if ok:
            factor.last_used_step = step
        elif step is None:
            method = "recovery_code"
            used = await db.execute(
                update(UserMfaRecoveryCode)
                .where(
                    UserMfaRecoveryCode.user_id == user.id,
                    UserMfaRecoveryCode.code_hash == _recovery_hash(keys, code),
                    UserMfaRecoveryCode.used_at.is_(None),
                )
                .values(used_at=datetime.now(UTC))
                .returning(UserMfaRecoveryCode.id)
            )
            ok = used.first() is not None
        if ok:
            await _audit(db, meta, user, "identity.mfa.verified", {"method": method})
            token = await _upgrade_session(db, rt, meta, user)
        else:
            await _audit(db, meta, user, "identity.mfa.failed")
    if token is None:
        raise MfaCodeInvalidError
    await limiter.reset(ratelimit.MFA_USER, str(user.id))
    return token


async def reset(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Remove a user's factor and recovery codes (Super Admin CLI, lost device). Caller commits."""
    await db.execute(delete(UserMfaFactor).where(UserMfaFactor.user_id == user_id))
    await db.execute(delete(UserMfaRecoveryCode).where(UserMfaRecoveryCode.user_id == user_id))
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), revoked_reason="mfa_reset")
    )


async def _upgrade_session(
    db: AsyncSession, rt: AuthRuntime, meta: ClientMeta, user: CurrentUser
) -> str:
    await revoke_session(db, user.session_id, "mfa_upgraded")
    return await create_session(
        db,
        user_id=user.id,
        settings=rt.settings,
        user_agent=meta.user_agent,
        ip_prefix=meta.ip_prefix,
        mfa_verified=True,
    )


async def _audit(
    db: AsyncSession,
    meta: ClientMeta,
    user: CurrentUser,
    action: str,
    changes: dict[str, str] | None = None,
) -> None:
    await audit.record(
        db,
        actor_id=user.id,
        action=action,
        entity_type="user",
        entity_id=user.id,
        changes=changes,
        request_id=meta.request_id,
        ip=meta.ip_prefix,
    )
