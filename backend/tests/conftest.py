import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Iterator

import asyncpg
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.main import create_app

# Real provider credentials may be in the developer's .env: tests never use them.
for _name in (
    "GEMINI_API_KEY",
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "SPEAKING_EVENTS_TOKEN",
):
    os.environ.pop(_name, None)

# Port 9 (discard) on loopback is not listening in CI or locally: dependency checks fail fast.
UNREACHABLE_DB = "postgresql://test:test@127.0.0.1:9/test"
UNREACHABLE_REDIS = "redis://127.0.0.1:9/0"

# --- Integration test configuration (real PostgreSQL / Redis) -----------------------------------
# TEST_DATABASE_ADMIN_URL: a role allowed to CREATE/DROP DATABASE, e.g.
#   postgresql://ielts:<password>@127.0.0.1:5432/postgres
# The suite creates and drops its own database named TEST_DATABASE_NAME; nothing else is touched.
TEST_DATABASE_NAME = "ielts_test"
_REQUIRE = os.environ.get("REQUIRE_INTEGRATION_TESTS") == "1"


def _integration_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        if _REQUIRE:
            pytest.fail(f"{name} must be set when REQUIRE_INTEGRATION_TESTS=1")
        pytest.skip(f"integration test: set {name} to run")
    return value


async def _recreate_database(admin_url: str, name: str, *, create: bool) -> None:
    conn = await asyncpg.connect(admin_url)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        if create:
            await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def test_database_url() -> Iterator[str]:
    """A fresh, empty database for the whole test session; dropped afterwards."""
    admin = make_url(_integration_env("TEST_DATABASE_ADMIN_URL"))
    assert TEST_DATABASE_NAME.endswith("_test")
    if admin.database == TEST_DATABASE_NAME:
        pytest.fail("TEST_DATABASE_ADMIN_URL must point at a maintenance DB, not the test DB")
    admin_dsn = admin.render_as_string(hide_password=False)
    asyncio.run(_recreate_database(admin_dsn, TEST_DATABASE_NAME, create=True))
    yield admin.set(database=TEST_DATABASE_NAME).render_as_string(hide_password=False)
    asyncio.run(_recreate_database(admin_dsn, TEST_DATABASE_NAME, create=False))


@pytest.fixture
def empty_database_url() -> Iterator[str]:
    """A brand-new empty database for one test (migration roundtrips must not see other data)."""
    admin = make_url(_integration_env("TEST_DATABASE_ADMIN_URL"))
    name = f"ielts_{uuid.uuid4().hex[:12]}_test"
    admin_dsn = admin.render_as_string(hide_password=False)
    asyncio.run(_recreate_database(admin_dsn, name, create=True))
    yield admin.set(database=name).render_as_string(hide_password=False)
    asyncio.run(_recreate_database(admin_dsn, name, create=False))


@pytest.fixture(scope="session")
def test_redis_url() -> str:
    return _integration_env("TEST_REDIS_URL")


# --- Unit test app (no real dependencies) -------------------------------------------------------
@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="ci",
        database_url=UNREACHABLE_DB,
        redis_url=UNREACHABLE_REDIS,
        readiness_timeout_seconds=0.5,
        db_connect_timeout_seconds=0.5,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    await app.state.db_engine.dispose()


@pytest.fixture(autouse=True)
def _no_real_ai_providers() -> Iterator[None]:
    """Tests never call a real AI provider, even when GEMINI_API_KEY is in the environment:
    each test starts with no providers and installs fakes explicitly."""
    from app.core import ai

    ai.use_providers(ai.Providers())
    yield
    ai.use_providers(ai.Providers())
