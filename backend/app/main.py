"""FastAPI application factory.

Run with: `uvicorn app.main:create_app --factory` (settings are read at startup, not import time).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.core.config import Settings, get_settings
from app.core.database import create_engine, create_session_factory
from app.core.errors import register_exception_handlers
from app.core.health import router as health_router
from app.core.logging import configure_logging
from app.core.request_context import RequestContextMiddleware
from app.modules.admin import api as admin
from app.modules.assistant import api as assistant
from app.modules.exams import api as exams
from app.modules.identity import api as identity
from app.modules.speaking import api as speaking
from app.modules.writing import api as writing


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    # Close pooled connections cleanly on shutdown.
    await app.state.db_engine.dispose()
    await app.state.redis.aclose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title="IELTS MASTER 2.0 API",
        version=__version__,
        docs_url="/api/v1/docs" if settings.docs_enabled else None,
        openapi_url="/api/v1/openapi.json" if settings.docs_enabled else None,
        redoc_url=None,
        lifespan=_lifespan,
    )
    app.state.settings = settings
    # Engine creation is lazy: no connection is opened until the first query.
    app.state.db_engine = create_engine(settings)
    app.state.db_session_factory = create_session_factory(app.state.db_engine)

    register_exception_handlers(app)
    app.include_router(health_router)
    # Domain modules mount their routers under /api/v1. Identity also adds the CSRF middleware,
    # which must sit inside RequestContextMiddleware (added last = outermost).
    identity.install(app, settings)
    admin.install(app)  # Super Admin console API; every route is staff- and permission-gated
    # Writing before exams: exams owns the generic /api/v1/{module}/tests (listening|reading).
    writing.install(app)  # candidate Writing drafts, submissions and AI evaluations
    speaking.install(app)  # candidate Speaking sessions, recordings and AI evaluations
    exams.install(app)  # candidate Listening practice and attempts (owner-only)
    assistant.install(app)  # floating site assistant (guests and users; no persistence)
    app.add_middleware(RequestContextMiddleware)
    return app
