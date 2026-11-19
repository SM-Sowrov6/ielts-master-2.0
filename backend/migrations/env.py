"""Alembic environment (async, asyncpg).

The URL comes from `DatabaseSettings` (env var DATABASE_URL), or from
`config.attributes["database_url"]` when invoked programmatically (tests).
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import URL, Connection
from sqlalchemy.ext.asyncio import create_async_engine

# Every model module must be imported here so autogenerate and `alembic check` see it.
import app.core.outbox
import app.modules.audit.models
import app.modules.content.models
import app.modules.exams.models
import app.modules.identity.models
import app.modules.speaking.models
import app.modules.writing.models  # noqa: F401
from app.core.config import DatabaseSettings
from app.core.database import sqlalchemy_url
from app.core.orm import Base

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> URL:
    override = config.attributes.get("database_url")
    raw = str(override) if override else str(DatabaseSettings().database_url)
    return sqlalchemy_url(raw)


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting (`alembic upgrade head --sql`)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(
        _database_url(),
        poolclass=pool.NullPool,
        connect_args={"server_settings": {"application_name": "ielts-migrations"}},
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
