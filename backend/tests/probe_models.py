"""Probe ORM models for database-foundation tests.

They use a separate MetaData (same naming convention and type map as `Base`) so they never
appear in `Base.metadata` and cannot cause false Alembic drift.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.orm import NAMING_CONVENTION, Base, TimestampMixin, UUIDPrimaryKeyMixin


class ProbeBase(DeclarativeBase):
    """Separate metadata so probe tables never appear in Base.metadata (Alembic drift checks)."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = Base.type_annotation_map


class ProbeParent(UUIDPrimaryKeyMixin, TimestampMixin, ProbeBase):
    __tablename__ = "probe_parent"
    __table_args__ = (CheckConstraint("length(code) > 0", name="code_not_empty"),)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(100), index=True)


class ProbeChild(UUIDPrimaryKeyMixin, ProbeBase):
    __tablename__ = "probe_child"
    parent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("probe_parent.id"))
    seen_at: Mapped[datetime]
