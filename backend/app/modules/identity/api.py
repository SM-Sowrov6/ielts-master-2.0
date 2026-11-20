"""Public interface of the identity module (docs/SYSTEM_ARCHITECTURE.md §3.2).

Other modules use only what is exported here: the authenticated principal and permission
dependencies. The application factory calls `install`; the outbox worker uses the handlers and
cleanup.
"""

from fastapi import FastAPI, Request
from redis.asyncio import Redis

from app.core.config import Settings
from app.modules.identity.consents import VOICE_CONSENT_VERSION, grant_voice_consents
from app.modules.identity.csrf import CsrfMiddleware
from app.modules.identity.deps import (
    current_user,
    optional_current_user,
    require_permission,
    require_staff,
    require_staff_permission,
)
from app.modules.identity.directory import UserOverview, display_names, user_overview
from app.modules.identity.emails import OUTBOX_HANDLERS, cleanup
from app.modules.identity.passwords import PasswordService
from app.modules.identity.ratelimit import RateLimiter, Rule
from app.modules.identity.router import router
from app.modules.identity.service import AuthRuntime
from app.modules.identity.sessions import CurrentUser
from app.modules.identity.tokens import AuthKeys

__all__ = [
    "OUTBOX_HANDLERS",
    "VOICE_CONSENT_VERSION",
    "CurrentUser",
    "RateLimiter",
    "Rule",
    "UserOverview",
    "cleanup",
    "current_user",
    "display_names",
    "grant_voice_consents",
    "install",
    "optional_current_user",
    "rate_limiter",
    "require_permission",
    "require_staff",
    "require_staff_permission",
    "user_overview",
]


def rate_limiter(request: Request) -> RateLimiter:
    """The shared Redis rate limiter, for other modules' quotas (hashed subjects, fixed windows)."""
    runtime: AuthRuntime = request.app.state.auth
    return runtime.limiter


def install(app: FastAPI, settings: Settings) -> None:
    """Wire identity into the app: runtime state, CSRF middleware and routes."""
    keys = AuthKeys.from_settings(settings)
    redis = Redis.from_url(str(settings.redis_url), socket_connect_timeout=1.0, socket_timeout=1.0)
    app.state.redis = redis
    app.state.auth = AuthRuntime(
        settings=settings,
        keys=keys,
        passwords=PasswordService(
            memory_kib=settings.password_hash_memory_kib,
            iterations=settings.password_hash_iterations,
            concurrency=settings.password_hash_concurrency,
        ),
        limiter=RateLimiter(redis),
    )
    app.add_middleware(CsrfMiddleware, settings=settings, keys=keys)
    app.include_router(router)
