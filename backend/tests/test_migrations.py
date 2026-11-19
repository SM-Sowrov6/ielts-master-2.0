"""Alembic migration tests. Synchronous on purpose: env.py runs its own event loop."""

import asyncio
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.exc import IntegrityError

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
REQUIRED_EXTENSIONS = {"citext", "pg_trgm", "vector"}
HEAD = "0013"


def _config(database_url: str | None = None) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["configure_logger"] = False
    if database_url:
        cfg.attributes["database_url"] = database_url
    return cfg


async def _fetch_column(url: str, sql: str) -> list[str]:
    conn = await asyncpg.connect(url)
    try:
        return [row[0] for row in await conn.fetch(sql)]
    finally:
        await conn.close()


def _installed_extensions(url: str) -> set[str]:
    rows = asyncio.run(_fetch_column(url, "SELECT extname FROM pg_extension"))
    return set(rows) & REQUIRED_EXTENSIONS


def _current_revision(url: str) -> list[str]:
    return asyncio.run(_fetch_column(url, "SELECT version_num FROM alembic_version"))


def test_single_linear_history() -> None:
    script = ScriptDirectory.from_config(_config())
    assert script.get_heads() == [HEAD]
    for revision in script.walk_revisions():
        assert revision.revision.isdigit()
        assert len(revision.revision) == 4  # sequential 4-digit IDs
        assert not revision.is_merge_point


@pytest.mark.integration
def test_upgrade_downgrade_upgrade_roundtrip(empty_database_url: str) -> None:
    cfg = _config(empty_database_url)

    command.upgrade(cfg, "head")
    assert _installed_extensions(empty_database_url) == REQUIRED_EXTENSIONS
    assert _current_revision(empty_database_url) == [HEAD]

    command.downgrade(cfg, "base")
    # Extensions are infrastructure: downgrade must never drop them (they may be admin-owned).
    assert _installed_extensions(empty_database_url) == REQUIRED_EXTENSIONS
    assert _current_revision(empty_database_url) == []

    command.upgrade(cfg, "head")
    assert _installed_extensions(empty_database_url) == REQUIRED_EXTENSIONS
    assert _current_revision(empty_database_url) == [HEAD]


@pytest.mark.integration
def test_preinstalled_extension_survives_full_downgrade(empty_database_url: str) -> None:
    """An extension present before the app's first migration is left untouched by downgrade."""
    cfg = _config(empty_database_url)
    command.downgrade(cfg, "base")
    asyncio.run(_fetch_column(empty_database_url, "CREATE EXTENSION IF NOT EXISTS citext"))
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    assert "citext" in _installed_extensions(empty_database_url)
    command.upgrade(cfg, "head")


@pytest.mark.integration
def test_upgrade_is_idempotent_at_head(test_database_url: str) -> None:
    cfg = _config(test_database_url)
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")  # no-op, must not fail
    assert _current_revision(test_database_url) == [HEAD]


@pytest.mark.integration
def test_models_and_migrations_have_no_drift(test_database_url: str) -> None:
    cfg = _config(test_database_url)
    command.upgrade(cfg, "head")
    command.check(cfg)  # raises if autogenerate would produce operations


@pytest.mark.integration
def test_downgrade_below_0004_is_blocked_while_content_exists(empty_database_url: str) -> None:
    """Safety net: content referencing seeded question types blocks a destructive downgrade."""
    cfg = _config(empty_database_url)
    command.upgrade(cfg, "head")
    asyncio.run(
        _fetch_column(
            empty_database_url,
            "WITH l AS (INSERT INTO content_licenses (id, source_type, licensor) "
            "VALUES (gen_random_uuid(), 'original', 'Synthetic') RETURNING id), "
            "b AS (INSERT INTO books (id, slug, title, license_id) "
            "SELECT gen_random_uuid(), 'synthetic-guard', 'Synthetic', id FROM l RETURNING id), "
            "e AS (INSERT INTO book_editions (id, book_id, edition_label, variant) "
            "SELECT gen_random_uuid(), id, '1st', 'academic' FROM b RETURNING id), "
            "t AS (INSERT INTO tests (id, edition_id, code, title) "
            "SELECT gen_random_uuid(), id, 'T1', 'Synthetic' FROM e RETURNING id), "
            "v AS (INSERT INTO test_versions (id, test_id, version_no) "
            "SELECT gen_random_uuid(), id, 1 FROM t RETURNING id), "
            "m AS (INSERT INTO test_modules (id, test_version_id, module, variant) "
            "SELECT gen_random_uuid(), id, 'reading', 'academic' FROM v RETURNING id), "
            "s AS (INSERT INTO sections (id, test_module_id, section_no) "
            "SELECT gen_random_uuid(), id, 1 FROM m RETURNING id) "
            "INSERT INTO question_groups (id, section_id, question_type) "
            "SELECT gen_random_uuid(), id, 'tfng' FROM s RETURNING id",
        )
    )
    with pytest.raises(IntegrityError, match="question_types"):
        command.downgrade(cfg, "0003")
    assert _current_revision(empty_database_url) == ["0004"]  # 0005 -> 0004 ran; 0004 refused


@pytest.mark.integration
def test_identity_downgrades_refuse_to_destroy_accounts_or_pending_email(
    empty_database_url: str,
) -> None:
    """0007 keeps undelivered email; 0006 keeps user accounts (no silent data loss)."""
    cfg = _config(empty_database_url)
    command.upgrade(cfg, "head")
    asyncio.run(
        _fetch_column(
            empty_database_url,
            "INSERT INTO outbox_messages (id, topic, payload) "
            "VALUES (gen_random_uuid(), 'test.topic', '{}') RETURNING id",
        )
    )
    with pytest.raises(RuntimeError, match="undelivered"):
        command.downgrade(cfg, "0006")
    assert _current_revision(empty_database_url) == ["0007"]

    asyncio.run(
        _fetch_column(
            empty_database_url,
            "UPDATE outbox_messages SET status = 'sent' RETURNING id",
        )
    )
    asyncio.run(
        _fetch_column(
            empty_database_url,
            "INSERT INTO users (id, email, password_hash) "
            "VALUES (gen_random_uuid(), 'guard@example.test', 'x') RETURNING id",
        )
    )
    with pytest.raises(RuntimeError, match="user account"):
        command.downgrade(cfg, "0005")
    assert _current_revision(empty_database_url) == ["0006"]  # 0007 dropped; 0006 refused


@pytest.mark.integration
def test_rbac_seed_matches_security_matrix(empty_database_url: str) -> None:
    command.upgrade(_config(empty_database_url), "head")
    rows = asyncio.run(
        _fetch_column(
            empty_database_url,
            "SELECT r.code || ':' || p.code FROM role_permissions rp "
            "JOIN roles r ON r.id = rp.role_id JOIN permissions p ON p.id = rp.permission_id",
        )
    )
    grants = set(rows)
    assert "student:admin.access" not in grants
    assert not any(g.startswith("student:") for g in grants)  # students: ownership, not perms
    for staff in ("super_admin", "admin", "content_manager", "reviewer"):
        assert f"{staff}:admin.access" in grants
    assert "super_admin:system.configure" in grants
    assert "admin:system.configure" not in grants
    assert "reviewer:content.publish" not in grants
    assert "content_manager:content.review" not in grants
