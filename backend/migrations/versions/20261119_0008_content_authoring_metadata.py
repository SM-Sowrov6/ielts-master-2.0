"""Authoring metadata for the admin content editor (Listening management, 2026-11-19).

Smallest extension of the content schema, no new tables:
- `test_versions.description`, `difficulty`, `tags`: versioned test metadata, frozen with the
  version once it leaves draft (the immutability guard is extended to cover them).
- `tests.admin_notes`: internal notes on the logical test (never exposed to students).
- `sections.context`: what the recording is about (e.g. "conversation about a gym membership").
- `media_assets.original_filename`, `uploaded_by`: upload provenance.

Difficulty reuses the existing easy/medium/hard values (shown as Beginner/Intermediate/Advanced).

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUARD_VERSION = """
CREATE OR REPLACE FUNCTION content_guard_test_version() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status IN ('published', 'archived') THEN
      RAISE EXCEPTION 'content_version_immutable: cannot delete a % version', OLD.status
        USING ERRCODE = 'P0001';
    END IF;
    RETURN OLD;
  END IF;

  IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
       (OLD.status = 'draft' AND NEW.status = 'in_review')
    OR (OLD.status = 'in_review' AND NEW.status IN ('draft', 'published'))
    OR (OLD.status = 'published' AND NEW.status = 'archived')
  ) THEN
    RAISE EXCEPTION 'content_invalid_transition: % -> %', OLD.status, NEW.status
      USING ERRCODE = 'P0001';
  END IF;

  -- Outside draft, only lifecycle columns may change.
  IF OLD.status <> 'draft' AND (
       NEW.test_id IS DISTINCT FROM OLD.test_id
    OR NEW.version_no IS DISTINCT FROM OLD.version_no
    OR NEW.change_note IS DISTINCT FROM OLD.change_note
    OR NEW.created_by IS DISTINCT FROM OLD.created_by
    OR NEW.created_at IS DISTINCT FROM OLD.created_at
    {extra}
  ) THEN
    RAISE EXCEPTION 'content_version_immutable: % version fields are read-only', OLD.status
      USING ERRCODE = 'P0001';
  END IF;
  RETURN NEW;
END $$;
"""
_METADATA_GUARD = """OR NEW.description IS DISTINCT FROM OLD.description
    OR NEW.difficulty IS DISTINCT FROM OLD.difficulty
    OR NEW.tags IS DISTINCT FROM OLD.tags"""


def upgrade() -> None:
    op.add_column("test_versions", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("test_versions", sa.Column("difficulty", sa.String(length=10), nullable=True))
    op.add_column(
        "test_versions",
        sa.Column(
            "tags", postgresql.ARRAY(sa.String(length=50)), server_default="{}", nullable=False
        ),
    )
    op.create_check_constraint(
        "ck_test_versions_difficulty",
        "test_versions",
        "difficulty IS NULL OR difficulty IN ('easy', 'medium', 'hard')",
    )
    op.add_column("tests", sa.Column("admin_notes", sa.Text(), nullable=True))
    op.add_column("sections", sa.Column("context", sa.Text(), nullable=True))
    op.add_column(
        "media_assets", sa.Column("original_filename", sa.String(length=255), nullable=True)
    )
    op.add_column("media_assets", sa.Column("uploaded_by", sa.Uuid(), nullable=True))
    op.execute(_GUARD_VERSION.replace("{extra}", _METADATA_GUARD))


def downgrade() -> None:
    op.execute(_GUARD_VERSION.replace("{extra}", ""))
    op.drop_column("media_assets", "uploaded_by")
    op.drop_column("media_assets", "original_filename")
    op.drop_column("sections", "context")
    op.drop_column("tests", "admin_notes")
    op.drop_constraint("ck_test_versions_difficulty", "test_versions", type_="check")
    op.drop_column("test_versions", "tags")
    op.drop_column("test_versions", "difficulty")
    op.drop_column("test_versions", "description")
