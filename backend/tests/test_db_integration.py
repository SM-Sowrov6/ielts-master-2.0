"""Database foundation tests against a real PostgreSQL (TEST_DATABASE_ADMIN_URL)."""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import Depends, FastAPI
from probe_models import ProbeBase as _ProbeBase
from probe_models import ProbeChild as _Child
from probe_models import ProbeParent as _Parent
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import DatabaseSettings, Settings
from app.core.database import create_engine, create_session_factory, get_db_session
from app.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine(test_database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(DatabaseSettings(database_url=test_database_url))
    async with engine.begin() as conn:
        await conn.run_sync(_ProbeBase.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(_ProbeBase.metadata.drop_all)
        await engine.dispose()


async def test_engine_connects_with_expected_server_and_application_name(
    engine: AsyncEngine,
) -> None:
    async with engine.connect() as conn:
        version = int((await conn.execute(text("SHOW server_version_num"))).scalar_one())
        app_name = (await conn.execute(text("SHOW application_name"))).scalar_one()
        timezone = (await conn.execute(text("SHOW TimeZone"))).scalar_one()
    assert version >= 170000  # docs: PostgreSQL 17+ (local/CI run 18)
    assert app_name == "ielts-backend"
    assert timezone in {"UTC", "Etc/UTC"}


async def test_constraint_names_exist_in_catalog(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        constraints = set(
            (
                await conn.execute(
                    text(
                        # p/u/c/f are governed by NAMING_CONVENTION. PostgreSQL 18 also lists
                        # NOT NULL constraints (contype 'n') with system names; those are excluded.
                        "SELECT conname FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
                        "WHERE t.relname IN ('probe_parent', 'probe_child') "
                        "AND c.contype IN ('p', 'u', 'c', 'f')"
                    )
                )
            ).scalars()
        )
        indexes = set(
            (
                await conn.execute(
                    text("SELECT indexname FROM pg_indexes WHERE tablename = 'probe_parent'")
                )
            ).scalars()
        )
    assert constraints == {
        "pk_probe_parent",
        "uq_probe_parent_code",
        "ck_probe_parent_code_not_empty",
        "pk_probe_child",
        "fk_probe_child_parent_id_probe_parent",
    }
    assert "ix_probe_parent_name" in indexes


async def test_insert_assigns_uuid7_and_server_timestamps(engine: AsyncEngine) -> None:
    factory = create_session_factory(engine)
    async with factory() as session, session.begin():
        parent = _Parent(code="P1", name="first")
        session.add(parent)
    assert parent.id.version == 7  # generated in the application before INSERT
    async with factory() as session:
        stored = await session.get_one(_Parent, parent.id)
    assert stored.created_at.tzinfo is not None
    assert stored.created_at == stored.updated_at


async def test_updated_at_refreshes_on_orm_update(engine: AsyncEngine) -> None:
    factory = create_session_factory(engine)
    async with factory() as session, session.begin():
        parent = _Parent(code="P2", name="before")
        session.add(parent)
    async with factory() as session, session.begin():
        loaded = await session.get_one(_Parent, parent.id)
        loaded.name = "after"
    async with factory() as session:
        stored = await session.get_one(_Parent, parent.id)
    assert stored.name == "after"
    assert stored.updated_at > stored.created_at


async def test_ids_sort_in_insertion_order(engine: AsyncEngine) -> None:
    factory = create_session_factory(engine)
    async with factory() as session, session.begin():
        parents = [_Parent(code=f"S{i}", name="ordered") for i in range(50)]
        session.add_all(parents)
    async with factory() as session:
        ordered = (
            await session.scalars(
                select(_Parent.code).where(_Parent.name == "ordered").order_by(_Parent.id)
            )
        ).all()
    assert list(ordered) == [p.code for p in parents]


async def test_foreign_key_and_check_constraints_are_enforced(engine: AsyncEngine) -> None:
    from datetime import UTC, datetime

    from sqlalchemy.exc import IntegrityError

    from app.shared.ids import new_id

    factory = create_session_factory(engine)
    with pytest.raises(IntegrityError):
        async with factory() as session, session.begin():
            session.add(_Child(parent_id=new_id(), seen_at=datetime.now(UTC)))
    with pytest.raises(IntegrityError):
        async with factory() as session, session.begin():
            session.add(_Parent(code="", name="empty code"))


# --- Request-scoped session dependency ----------------------------------------------------------
@pytest.fixture
async def app_with_db(
    test_database_url: str, test_redis_url: str, engine: AsyncEngine
) -> AsyncIterator[FastAPI]:
    app = create_app(
        Settings(app_env="ci", database_url=test_database_url, redis_url=test_redis_url)
    )

    @app.post("/_test/commit/{code}")
    async def commit(code: str, session: AsyncSession = Depends(get_db_session)) -> None:  # noqa: B008
        async with session.begin():
            session.add(_Parent(code=code, name="via-request"))

    @app.post("/_test/fail/{code}")
    async def fail(code: str, session: AsyncSession = Depends(get_db_session)) -> None:  # noqa: B008
        session.add(_Parent(code=code, name="via-request"))
        await session.flush()  # row written inside the open transaction...
        raise RuntimeError("boom")  # ...then the request fails

    yield app
    await app.state.db_engine.dispose()


async def _codes(engine: AsyncEngine) -> set[str]:
    factory = create_session_factory(engine)
    async with factory() as session:
        result = await session.scalars(select(_Parent.code).where(_Parent.name == "via-request"))
        return set(result.all())


async def test_request_session_commits_and_rolls_back(
    app_with_db: FastAPI, engine: AsyncEngine
) -> None:
    transport = httpx.ASGITransport(app=app_with_db, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        assert (await client.post("/_test/commit/R1")).status_code == 200
        assert (await client.post("/_test/fail/R2")).status_code == 500
    assert await _codes(engine) == {"R1"}


async def test_readyz_ok_against_real_postgres_and_redis(app_with_db: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app_with_db)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"postgres": "ok", "redis": "ok"}}
