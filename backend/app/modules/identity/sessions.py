"""Opaque server-side sessions and their cookies (ADR-006 revised; SECURITY_GUIDELINES.md §2-3).

- Login always creates a brand-new random token (no session fixation). The database stores its
  SHA-256 hash; the browser stores the token in an HttpOnly, SameSite=Lax cookie (`__Host-`
  prefix and Secure outside local development).
- A session is valid while not revoked, before its idle and absolute expiry, and while the user
  is `active`. The idle window slides forward at most every 5 minutes (bounded DB writes) and
  never past the absolute expiry.
- Every request re-reads the user's status, roles and permissions from the database, so
  suspension, role changes and revocation take effect immediately.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Response
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.identity.models import (
    AuthSession,
    Permission,
    Role,
    RolePermission,
    User,
    UserProfile,
    UserRole,
    UserStatus,
)
from app.modules.identity.tokens import hash_token, new_session_token
from app.shared.ids import new_id

SLIDE_INTERVAL = timedelta(minutes=5)
MAX_COOKIE_LENGTH = 100


@dataclass(frozen=True)
class CookieNames:
    session: str
    csrf: str


def cookie_names(settings: Settings) -> CookieNames:
    if settings.cookie_secure_effective:
        return CookieNames(session="__Host-session", csrf="__Host-csrf")
    return CookieNames(session="ielts_session", csrf="ielts_csrf")


@dataclass(frozen=True)
class CurrentUser:
    """The authenticated principal for one request. Never built from client-supplied data."""

    id: uuid.UUID
    email: str
    full_name: str
    email_verified: bool
    roles: frozenset[str]
    permissions: frozenset[str]
    session_id: uuid.UUID

    def has(self, permission: str) -> bool:
        return permission in self.permissions


def set_session_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        cookie_names(settings).session,
        token,
        max_age=settings.session_absolute_ttl_seconds,
        path="/",
        secure=settings.cookie_secure_effective,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        cookie_names(settings).session,
        path="/",
        secure=settings.cookie_secure_effective,
        httponly=True,
        samesite="lax",
    )


async def create_session(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    settings: Settings,
    user_agent: str | None,
    ip_prefix: str | None,
) -> str:
    """Insert a session in the caller's transaction and return the raw token (cookie only)."""
    token = new_session_token()
    now = datetime.now(UTC)
    absolute = now + timedelta(seconds=settings.session_absolute_ttl_seconds)
    db.add(
        AuthSession(
            id=new_id(),
            user_id=user_id,
            token_hash=hash_token(token),
            idle_expires_at=min(
                now + timedelta(seconds=settings.session_idle_ttl_seconds), absolute
            ),
            absolute_expires_at=absolute,
            user_agent=(user_agent or "")[:300] or None,
            ip_prefix=ip_prefix,
        )
    )
    return token


async def revoke_session(db: AsyncSession, session_id: uuid.UUID, reason: str) -> None:
    await db.execute(
        update(AuthSession)
        .where(AuthSession.id == session_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=func.now(), revoked_reason=reason)
    )


async def revoke_session_by_token(db: AsyncSession, token: str, reason: str) -> None:
    await db.execute(
        update(AuthSession)
        .where(AuthSession.token_hash == hash_token(token), AuthSession.revoked_at.is_(None))
        .values(revoked_at=func.now(), revoked_reason=reason)
    )


async def revoke_all_sessions(db: AsyncSession, user_id: uuid.UUID, reason: str) -> int:
    result = await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=func.now(), revoked_reason=reason)
        .returning(AuthSession.id)
    )
    return len(result.all())


async def load_principal(
    db: AsyncSession, user: User, full_name: str, session_id: uuid.UUID
) -> CurrentUser:
    roles = (
        await db.scalars(
            select(Role.code)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
        )
    ).all()
    permissions = (
        await db.scalars(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == user.id)
            .distinct()
        )
    ).all()
    return CurrentUser(
        id=user.id,
        email=user.email,
        full_name=full_name,
        email_verified=user.email_verified_at is not None,
        roles=frozenset(roles),
        permissions=frozenset(permissions),
        session_id=session_id,
    )


async def resolve_session(db: AsyncSession, token: str, settings: Settings) -> CurrentUser | None:
    """Look up a live session by token; slide its idle expiry. Caller owns the transaction."""
    if not token or len(token) > MAX_COOKIE_LENGTH:
        return None
    now = func.now()
    row = (
        await db.execute(
            select(AuthSession, User, UserProfile.full_name)
            .join(User, User.id == AuthSession.user_id)
            .join(UserProfile, UserProfile.user_id == User.id)
            .where(
                and_(
                    AuthSession.token_hash == hash_token(token),
                    AuthSession.revoked_at.is_(None),
                    AuthSession.idle_expires_at > now,
                    AuthSession.absolute_expires_at > now,
                    User.status == UserStatus.ACTIVE.value,
                )
            )
        )
    ).one_or_none()
    if row is None:
        return None
    auth_session, user, full_name = row
    if auth_session.last_seen_at < datetime.now(UTC) - SLIDE_INTERVAL:
        idle = timedelta(seconds=settings.session_idle_ttl_seconds)
        await db.execute(
            update(AuthSession)
            .where(AuthSession.id == auth_session.id)
            .values(
                last_seen_at=func.now(),
                idle_expires_at=func.least(func.now() + idle, AuthSession.absolute_expires_at),
            )
        )
    return await load_principal(db, user, full_name, auth_session.id)
