"""Database foundation unit tests — no database connection required."""

from typing import cast

import pytest
from probe_models import ProbeChild as _Child
from probe_models import ProbeParent as _Parent
from pydantic import ValidationError
from sqlalchemy import Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlalchemy.sql.elements import ClauseElement

from app.core.config import DatabaseSettings
from app.core.database import sqlalchemy_url
from app.core.orm import NAMING_CONVENTION, Base
from app.shared.ids import new_id

PARENT = cast(Table, _Parent.__table__)
CHILD = cast(Table, _Child.__table__)


def _ddl(element: ClauseElement) -> str:
    return str(element.compile(dialect=postgresql.dialect()))  # type: ignore[no-untyped-call]


# --- IDs ----------------------------------------------------------------------------------------
def test_new_id_is_uuid_version_7() -> None:
    assert new_id().version == 7


def test_new_ids_are_unique_and_time_ordered() -> None:
    ids = [new_id() for _ in range(2000)]
    assert len(set(ids)) == len(ids)
    assert ids == sorted(ids)  # monotonic within a process (B-tree friendly)


# --- Naming conventions & mixins ----------------------------------------------------------------
def test_base_uses_the_documented_naming_convention() -> None:
    assert Base.metadata.naming_convention == NAMING_CONVENTION
    # Every mapped table name is snake_case (convention-derived constraint names depend on it).
    assert Base.metadata.tables
    assert all(name == name.lower() and " " not in name for name in Base.metadata.tables)


def test_constraint_and_index_names_follow_convention() -> None:
    parent_ddl = _ddl(CreateTable(PARENT))
    child_ddl = _ddl(CreateTable(CHILD))
    index_ddl = [_ddl(CreateIndex(ix)) for ix in PARENT.indexes]

    assert "CONSTRAINT pk_probe_parent PRIMARY KEY (id)" in parent_ddl
    assert "CONSTRAINT uq_probe_parent_code UNIQUE (code)" in parent_ddl
    assert "CONSTRAINT ck_probe_parent_code_not_empty CHECK" in parent_ddl
    assert "CONSTRAINT fk_probe_child_parent_id_probe_parent FOREIGN KEY" in child_ddl
    assert index_ddl == ["CREATE INDEX ix_probe_parent_name ON probe_parent (name)"]


def test_mixin_columns_are_uuid_and_timestamptz_not_null_with_server_defaults() -> None:
    ddl = _ddl(CreateTable(PARENT))
    assert "id UUID NOT NULL" in ddl
    assert "created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in ddl
    assert "updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in ddl
    # Plain `Mapped[datetime]` columns are timestamptz too (type_annotation_map).
    assert "seen_at TIMESTAMP WITH TIME ZONE NOT NULL" in _ddl(CreateTable(CHILD))


def test_primary_key_default_is_application_generated() -> None:
    column = PARENT.c.id
    assert column.server_default is None
    assert column.default is not None
    # SQLAlchemy wraps callable defaults (keeping the name), so compare by name.
    assert getattr(getattr(column.default, "arg", None), "__name__", None) == "new_id"


# --- URL & settings -----------------------------------------------------------------------------
def test_sqlalchemy_url_switches_to_asyncpg_and_keeps_credentials() -> None:
    url = sqlalchemy_url("postgresql://user:p%40ss@db.internal:5432/ielts")
    assert url.drivername == "postgresql+asyncpg"
    assert (url.username, url.password, url.host, url.port, url.database) == (
        "user",
        "p@ss",
        "db.internal",
        5432,
        "ielts",
    )


def test_sqlalchemy_url_rejects_non_postgresql() -> None:
    with pytest.raises(ValueError, match="PostgreSQL"):
        sqlalchemy_url("mysql://user@host/db")


def test_database_settings_defaults_and_bounds() -> None:
    settings = DatabaseSettings(database_url="postgresql://u:p@h/d")
    assert (settings.db_pool_size, settings.db_max_overflow) == (5, 10)
    with pytest.raises(ValidationError):
        DatabaseSettings(database_url="postgresql://u:p@h/d", db_pool_size=0)
