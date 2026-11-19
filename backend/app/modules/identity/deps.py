"""FastAPI dependencies: the authenticated principal and server-side permission checks.

Authorization never trusts client-supplied role data: the principal is rebuilt from the
database on every request (sessions.resolve_session).
"""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request

from app.modules.identity.errors import (
    MfaRequiredError,
    NotAuthenticatedError,
    PermissionDeniedError,
)
from app.modules.identity.service import AuthRuntime, ClientMeta
from app.modules.identity.sessions import CurrentUser, cookie_names, resolve_session

_UNRESOLVED = object()


def auth_runtime(request: Request) -> AuthRuntime:
    runtime: AuthRuntime = request.app.state.auth
    return runtime


def client_meta(request: Request) -> ClientMeta:
    return ClientMeta(
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "request_id", None),
    )


def session_token(request: Request) -> str | None:
    return request.cookies.get(cookie_names(auth_runtime(request).settings).session)


async def optional_current_user(request: Request) -> CurrentUser | None:
    cached = getattr(request.state, "current_user", _UNRESOLVED)
    if cached is not _UNRESOLVED:
        return cached  # type: ignore[return-value]
    token = session_token(request)
    user: CurrentUser | None = None
    if token:
        factory = request.app.state.db_session_factory
        async with factory() as db, db.begin():
            user = await resolve_session(db, token, auth_runtime(request).settings)
    request.state.current_user = user
    return user


async def current_user(
    user: Annotated[CurrentUser | None, Depends(optional_current_user)],
) -> CurrentUser:
    if user is None:
        raise NotAuthenticatedError
    return user


def require_permission(code: str) -> Callable[..., Awaitable[CurrentUser]]:
    """Dependency factory: `Depends(require_permission("content.publish"))`."""

    async def dependency(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
        if not user.has(code):
            raise PermissionDeniedError
        return user

    return dependency


async def require_staff(
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("admin.access"))],
) -> CurrentUser:
    """Staff area gate. Wherever STAFF_MFA_REQUIRED is in effect (always in production; off by
    default only in local/ci) the session must have passed the second factor (identity/mfa.py);
    otherwise 403 `mfa_required` sends the client to enrol or verify."""
    if auth_runtime(request).settings.staff_mfa_required_effective and not user.mfa_verified:
        raise MfaRequiredError
    return user


def require_staff_permission(*codes: str) -> Callable[..., Awaitable[CurrentUser]]:
    """Gate for every admin API: the staff gate above (admin.access + staff 2FA where required)
    AND at least one of `codes`. Fails 401 (no live session) or 403 (not allowed)."""
    if not codes:
        raise ValueError("require_staff_permission needs at least one permission code")

    async def dependency(user: Annotated[CurrentUser, Depends(require_staff)]) -> CurrentUser:
        if not any(user.has(code) for code in codes):
            raise PermissionDeniedError
        return user

    return dependency
