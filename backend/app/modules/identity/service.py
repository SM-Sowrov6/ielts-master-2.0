"""Identity use cases (docs/SECURITY_GUIDELINES.md §2-3, API_SPECIFICATION.md §2).

Rules that apply throughout:
- Responses for register / resend / forgot are identical whether or not the email is known
  (no account enumeration); work that would differ (hashing) is done on both paths.
- One-time tokens are created inside the request transaction together with their outbox
  message (see tokens.py); raw tokens are never stored.
- Email verification and password reset are separate lifecycles: a reset never verifies an
  email, and verification never changes a password.
- Audit entries carry the user id (never the email) and a truncated IP prefix.
"""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import DEV_PLACEHOLDER, Settings
from app.core.outbox import enqueue
from app.modules.audit import api as audit
from app.modules.identity import emails, ratelimit
from app.modules.identity.errors import (
    ConsentRequiredError,
    CurrentPasswordIncorrectError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    PasswordPolicyError,
    RegistrationClosedError,
    TokenInvalidError,
)
from app.modules.identity.models import (
    ConsentType,
    OneTimeToken,
    Role,
    TokenPurpose,
    User,
    UserConsent,
    UserProfile,
    UserRole,
    UserStatus,
)
from app.modules.identity.passwords import PasswordService, policy_problem
from app.modules.identity.ratelimit import RateLimiter
from app.modules.identity.schemas import RegisterRequest
from app.modules.identity.sessions import (
    CurrentUser,
    create_session,
    resolve_session,
    revoke_all_sessions,
    revoke_session_by_token,
)
from app.modules.identity.tokens import (
    AuthKeys,
    derive_one_time_token,
    hash_token,
    ip_prefix,
    looks_like_token,
    new_salt,
)
from app.shared.ids import new_id

VERIFY_EMAIL_TTL = timedelta(hours=24)
RESET_PASSWORD_TTL = timedelta(minutes=30)
TOKEN_TTL = {
    TokenPurpose.VERIFY_EMAIL: VERIFY_EMAIL_TTL,
    TokenPurpose.RESET_PASSWORD: RESET_PASSWORD_TTL,
}
TOKEN_TOPIC = {
    TokenPurpose.VERIFY_EMAIL: emails.TOPIC_VERIFY_EMAIL,
    TokenPurpose.RESET_PASSWORD: emails.TOPIC_RESET_PASSWORD,
}
ROLE_STUDENT = "student"


@dataclass(frozen=True)
class AuthRuntime:
    settings: Settings
    keys: AuthKeys
    passwords: PasswordService
    limiter: RateLimiter


@dataclass(frozen=True)
class ClientMeta:
    ip: str | None
    user_agent: str | None
    request_id: str | None

    @property
    def ip_prefix(self) -> str | None:
        return ip_prefix(self.ip)

    @property
    def rate_subject(self) -> str:
        return self.ip or "unknown"


async def _audit(
    db: AsyncSession,
    meta: ClientMeta,
    action: str,
    *,
    user_id: uuid.UUID | None,
    actor: uuid.UUID | None = None,
    changes: dict[str, str] | None = None,
) -> None:
    await audit.record(
        db,
        actor_id=actor,
        action=action,
        entity_type="user",
        entity_id=user_id,
        changes=changes,
        request_id=meta.request_id,
        ip=meta.ip_prefix,
    )


async def _issue_token(
    db: AsyncSession, keys: AuthKeys, user_id: uuid.UUID, purpose: TokenPurpose
) -> None:
    """Supersede older tokens of this purpose, store the new hash and its outbox message."""
    await db.execute(
        update(OneTimeToken)
        .where(
            OneTimeToken.user_id == user_id,
            OneTimeToken.purpose == purpose.value,
            OneTimeToken.consumed_at.is_(None),
        )
        .values(consumed_at=func.now())
    )
    salt = new_salt()
    raw = derive_one_time_token(keys.one_time_token, purpose.value, salt)
    token_id = new_id()
    db.add(
        OneTimeToken(
            id=token_id,
            user_id=user_id,
            purpose=purpose.value,
            token_hash=hash_token(raw),
            expires_at=datetime.now(UTC) + TOKEN_TTL[purpose],
        )
    )
    enqueue(db, TOKEN_TOPIC[purpose], emails.token_payload(token_id, salt))


async def _consume_token(db: AsyncSession, raw: str, purpose: TokenPurpose) -> uuid.UUID | None:
    """Atomically mark a valid token used. Concurrent or repeated use gets None."""
    result = await db.execute(
        update(OneTimeToken)
        .where(
            OneTimeToken.token_hash == hash_token(raw),
            OneTimeToken.purpose == purpose.value,
            OneTimeToken.consumed_at.is_(None),
            OneTimeToken.expires_at > func.now(),
        )
        .values(consumed_at=func.now())
        .returning(OneTimeToken.user_id)
    )
    return result.scalar_one_or_none()


async def _check_password(password: str, email: str) -> None:
    problem = policy_problem(password, email=email)
    if problem is not None:
        raise PasswordPolicyError(problem)


# --- Registration & verification ------------------------------------------------------------
async def register(
    db: AsyncSession, rt: AuthRuntime, meta: ClientMeta, data: RegisterRequest
) -> None:
    settings = rt.settings
    if not settings.registration_open:
        raise RegistrationClosedError
    await rt.limiter.enforce(ratelimit.REGISTER_IP, meta.rate_subject)
    if not data.accept_terms or not data.age_confirmation:
        raise ConsentRequiredError
    await _check_password(data.password, data.email)
    password_hash = await rt.passwords.hash(data.password)
    email_allowed = await rt.limiter.allow(ratelimit.EMAIL_ACCOUNT, data.email.casefold())
    try:
        async with db.begin():
            await _register_in_transaction(db, rt, meta, data, password_hash, email_allowed)
    except IntegrityError:
        # A concurrent registration of the same email won the race: answer exactly as for any
        # existing account.
        async with db.begin():
            await _register_in_transaction(db, rt, meta, data, password_hash, email_allowed)


async def _register_in_transaction(
    db: AsyncSession,
    rt: AuthRuntime,
    meta: ClientMeta,
    data: RegisterRequest,
    password_hash: str,
    email_allowed: bool,
) -> None:
    existing = await db.scalar(select(User).where(User.email == data.email))
    if existing is not None:
        if email_allowed and existing.status == UserStatus.PENDING.value:
            await _issue_token(db, rt.keys, existing.id, TokenPurpose.VERIFY_EMAIL)
        elif email_allowed and existing.status == UserStatus.ACTIVE.value:
            enqueue(db, emails.TOPIC_ACCOUNT_EXISTS, emails.user_payload(existing.id))
        await _audit(db, meta, "identity.registration.duplicate", user_id=existing.id)
        return

    settings = rt.settings
    user_id = new_id()
    db.add(User(id=user_id, email=data.email, password_hash=password_hash))
    db.add(UserProfile(user_id=user_id, full_name=data.full_name))
    age_version = (
        f"minimum-age:{settings.registration_minimum_age}"
        if settings.registration_minimum_age is not None
        else DEV_PLACEHOLDER
    )
    for consent_type, version in (
        (ConsentType.TERMS, settings.terms_version_effective),
        (ConsentType.PRIVACY, settings.privacy_version_effective),
        (ConsentType.AGE_CONFIRMATION, age_version),
    ):
        db.add(
            UserConsent(
                id=new_id(),
                user_id=user_id,
                consent_type=consent_type.value,
                document_version=version,
                granted=True,
            )
        )
    student_role = await db.scalar(select(Role.id).where(Role.code == ROLE_STUDENT))
    if student_role is None:
        raise RuntimeError("Role 'student' is missing: run database migrations")
    db.add(UserRole(user_id=user_id, role_id=student_role))
    await db.flush()  # surfaces a unique-email race here, inside the caller's try
    if email_allowed:
        await _issue_token(db, rt.keys, user_id, TokenPurpose.VERIFY_EMAIL)
    await _audit(db, meta, "identity.user.registered", user_id=user_id, actor=user_id)


async def verify_email(db: AsyncSession, rt: AuthRuntime, meta: ClientMeta, raw: str) -> None:
    await rt.limiter.enforce(ratelimit.VERIFY_IP, meta.rate_subject)
    if not looks_like_token(raw):
        raise TokenInvalidError
    async with db.begin():
        user_id = await _consume_token(db, raw, TokenPurpose.VERIFY_EMAIL)
        if user_id is None:
            raise TokenInvalidError
        await db.execute(
            update(User)
            .where(User.id == user_id, User.email_verified_at.is_(None))
            .values(email_verified_at=func.now())
        )
        await db.execute(
            update(User)
            .where(User.id == user_id, User.status == UserStatus.PENDING.value)
            .values(status=UserStatus.ACTIVE.value)
        )
        await _audit(db, meta, "identity.email.verified", user_id=user_id, actor=user_id)


async def resend_verification(
    db: AsyncSession, rt: AuthRuntime, meta: ClientMeta, email: str
) -> None:
    await rt.limiter.enforce(ratelimit.RESEND_IP, meta.rate_subject)
    async with db.begin():
        user = await db.scalar(select(User).where(User.email == email))
        if user is None or user.status != UserStatus.PENDING.value:
            return
        if not await rt.limiter.allow(ratelimit.EMAIL_ACCOUNT, email.casefold()):
            return
        await _issue_token(db, rt.keys, user.id, TokenPurpose.VERIFY_EMAIL)
        await _audit(db, meta, "identity.verification.resent", user_id=user.id)


# --- Sessions -----------------------------------------------------------------------------------
async def login(
    db: AsyncSession,
    rt: AuthRuntime,
    meta: ClientMeta,
    *,
    email: str,
    password: str,
    previous_token: str | None,
) -> tuple[str, CurrentUser]:
    """Returns (new session token, principal). Always issues a NEW session (no fixation)."""
    await rt.limiter.enforce(ratelimit.LOGIN_IP, meta.rate_subject)
    account = email.casefold()
    await rt.limiter.ensure_below(ratelimit.LOGIN_ACCOUNT_FAILURES, account)
    async with db.begin():
        user = await db.scalar(select(User).where(User.email == email))
    password_ok = await rt.passwords.verify(user.password_hash if user else None, password)
    allowed = user is not None and user.status in (
        UserStatus.ACTIVE.value,
        UserStatus.PENDING.value,
    )
    if not password_ok or not allowed or user is None:
        failures, _ = await rt.limiter.hit(ratelimit.LOGIN_ACCOUNT_FAILURES, account)
        async with db.begin():
            await _audit(
                db,
                meta,
                "identity.login.failed",
                user_id=user.id if user else None,
                changes={"reason": "status" if password_ok else "credentials"},
            )
        if failures > 3:  # progressive delay slows online guessing further
            await asyncio.sleep(min(0.25 * 2 ** (failures - 4), 2.0))
        raise InvalidCredentialsError
    if user.status == UserStatus.PENDING.value:
        async with db.begin():
            await _audit(db, meta, "identity.login.unverified", user_id=user.id)
        raise EmailNotVerifiedError
    await rt.limiter.reset(ratelimit.LOGIN_ACCOUNT_FAILURES, account)
    new_hash = (
        await rt.passwords.hash(password) if rt.passwords.needs_rehash(user.password_hash) else None
    )
    async with db.begin():
        if previous_token:
            await revoke_session_by_token(db, previous_token, "replaced_by_login")
        token = await create_session(
            db,
            user_id=user.id,
            settings=rt.settings,
            user_agent=meta.user_agent,
            ip_prefix=meta.ip_prefix,
        )
        values: dict[str, object] = {"last_login_at": func.now()}
        if new_hash is not None:
            values["password_hash"] = new_hash
        await db.execute(update(User).where(User.id == user.id).values(**values))
        await _audit(db, meta, "identity.login.succeeded", user_id=user.id, actor=user.id)
        await db.flush()
        principal = await resolve_session(db, token, rt.settings)
    if principal is None:  # pragma: no cover — the session was just created
        raise RuntimeError("New session could not be resolved")
    return token, principal


async def logout(
    db: AsyncSession, meta: ClientMeta, *, user: CurrentUser | None, token: str | None
) -> None:
    if not token:
        return
    async with db.begin():
        await revoke_session_by_token(db, token, "logout")
        if user is not None:
            await _audit(db, meta, "identity.logout", user_id=user.id, actor=user.id)


async def logout_all(db: AsyncSession, meta: ClientMeta, user: CurrentUser) -> None:
    async with db.begin():
        count = await revoke_all_sessions(db, user.id, "logout_all")
        await _audit(
            db,
            meta,
            "identity.logout_all",
            user_id=user.id,
            actor=user.id,
            changes={"sessions": str(count)},
        )


# --- Passwords ----------------------------------------------------------------------------------
async def forgot_password(db: AsyncSession, rt: AuthRuntime, meta: ClientMeta, email: str) -> None:
    await rt.limiter.enforce(ratelimit.FORGOT_IP, meta.rate_subject)
    async with db.begin():
        user = await db.scalar(select(User).where(User.email == email))
        if user is None or user.status not in (UserStatus.ACTIVE.value, UserStatus.PENDING.value):
            return
        if not await rt.limiter.allow(ratelimit.EMAIL_ACCOUNT, email.casefold()):
            return
        await _issue_token(db, rt.keys, user.id, TokenPurpose.RESET_PASSWORD)
        await _audit(db, meta, "identity.password.reset_requested", user_id=user.id)


async def reset_password(
    db: AsyncSession, rt: AuthRuntime, meta: ClientMeta, *, raw: str, new_password: str
) -> None:
    """Set a new password from a reset link. Does NOT verify the email (separate lifecycle)."""
    await rt.limiter.enforce(ratelimit.RESET_IP, meta.rate_subject)
    if not looks_like_token(raw):
        raise TokenInvalidError
    async with db.begin():
        row = (
            await db.execute(
                select(User.id, User.email)
                .join(OneTimeToken, OneTimeToken.user_id == User.id)
                .where(
                    OneTimeToken.token_hash == hash_token(raw),
                    OneTimeToken.purpose == TokenPurpose.RESET_PASSWORD.value,
                    OneTimeToken.consumed_at.is_(None),
                    OneTimeToken.expires_at > func.now(),
                    User.status.in_((UserStatus.ACTIVE.value, UserStatus.PENDING.value)),
                )
            )
        ).one_or_none()
    if row is None:
        raise TokenInvalidError
    user_id, email = row
    await _check_password(new_password, email)  # token stays usable if the password is rejected
    new_hash = await rt.passwords.hash(new_password)
    async with db.begin():
        if await _consume_token(db, raw, TokenPurpose.RESET_PASSWORD) != user_id:
            raise TokenInvalidError  # used concurrently, or expired meanwhile
        await db.execute(
            update(OneTimeToken)
            .where(
                OneTimeToken.user_id == user_id,
                OneTimeToken.purpose == TokenPurpose.RESET_PASSWORD.value,
                OneTimeToken.consumed_at.is_(None),
            )
            .values(consumed_at=func.now())
        )
        await db.execute(update(User).where(User.id == user_id).values(password_hash=new_hash))
        await revoke_all_sessions(db, user_id, "password_reset")
        enqueue(db, emails.TOPIC_PASSWORD_CHANGED, emails.user_payload(user_id))
        await _audit(db, meta, "identity.password.reset_completed", user_id=user_id, actor=user_id)


async def change_password(
    db: AsyncSession,
    rt: AuthRuntime,
    meta: ClientMeta,
    user: CurrentUser,
    *,
    current_password: str,
    new_password: str,
) -> str:
    """Change the password, revoke every session and return a fresh token for this browser."""
    await rt.limiter.enforce(ratelimit.PASSWORD_CHANGE_USER, str(user.id))
    async with db.begin():
        stored = await db.scalar(select(User.password_hash).where(User.id == user.id))
    if stored is None or not await rt.passwords.verify(stored, current_password):
        async with db.begin():
            await _audit(
                db, meta, "identity.password.change_failed", user_id=user.id, actor=user.id
            )
        raise CurrentPasswordIncorrectError
    await _check_password(new_password, user.email)
    new_hash = await rt.passwords.hash(new_password)
    async with db.begin():
        await db.execute(update(User).where(User.id == user.id).values(password_hash=new_hash))
        await revoke_all_sessions(db, user.id, "password_changed")
        token = await create_session(
            db,
            user_id=user.id,
            settings=rt.settings,
            user_agent=meta.user_agent,
            ip_prefix=meta.ip_prefix,
        )
        enqueue(db, emails.TOPIC_PASSWORD_CHANGED, emails.user_payload(user.id))
        await _audit(db, meta, "identity.password.changed", user_id=user.id, actor=user.id)
    return token
