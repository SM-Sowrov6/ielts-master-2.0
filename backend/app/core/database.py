"""Async database engine and session lifecycle (SQLAlchemy 2.x, asyncpg driver).

One engine (connection pool) per process, created with the app and disposed on shutdown.
Requests get a session via `get_db_session`; services own transaction boundaries
(`async with session.begin(): ...`) per docs/DEVELOPMENT_GUIDELINES.md §2.
"""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import DatabaseSettings

APPLICATION_NAME = "ielts-backend"


def sqlalchemy_url(database_url: str) -> URL:
    """Map a `postgresql://` DSN to the asyncpg dialect, preserving credentials and options."""
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("DATABASE_URL must be a PostgreSQL URL")
    return url.set(drivername="postgresql+asyncpg")


def create_engine(
    settings: DatabaseSettings, *, application_name: str = APPLICATION_NAME
) -> AsyncEngine:
    """Create the process-wide engine. No connection is opened until first use."""
    return create_async_engine(
        sqlalchemy_url(str(settings.database_url)),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_recycle=settings.db_pool_recycle_seconds,
        pool_pre_ping=True,
        echo=settings.db_echo,
        connect_args={
            "timeout": settings.db_connect_timeout_seconds,
            "server_settings": {"application_name": application_name},
        },
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: ORM objects stay readable after commit in async code.
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, always closed; rolled back if not committed."""
    factory: async_sessionmaker[AsyncSession] = request.app.state.db_session_factory
    async with factory() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise
