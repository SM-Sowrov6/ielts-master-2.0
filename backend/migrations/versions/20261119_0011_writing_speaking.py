"""Writing and Speaking: rubric versions, submissions, recordings and AI evaluations
(docs/DATABASE_SCHEMA.md §6, simplified for the first release).

- `rubric_versions` / `rubric_reviews`: platform-authored assessment criteria, versioned, with
  four-eyes review. Criteria are immutable once the version leaves draft (trigger).
- `writing_submissions`: one draft per user and task; immutable once submitted (trigger).
- `writing_evaluations` / `speaking_evaluations`: one row per evaluation run (retries add rows);
  bands only from a validated provider result, never defaults.
- `speaking_sessions` / `speaking_recordings`: consent ids are required; audio lives in private
  object storage (key per recording) and is purged after `audio_purge_after`.
- `sample_answers` (model answers) join the content immutability guard.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GUARDS = """
CREATE OR REPLACE FUNCTION rubric_versions_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'draft' THEN
      RAISE EXCEPTION 'content_version_immutable: cannot delete a % rubric', OLD.status
        USING ERRCODE = 'P0001';
    END IF;
    RETURN OLD;
  END IF;
  IF OLD.status <> 'draft' AND (NEW.criteria IS DISTINCT FROM OLD.criteria
      OR NEW.title IS DISTINCT FROM OLD.title OR NEW.module IS DISTINCT FROM OLD.module) THEN
    RAISE EXCEPTION 'content_version_immutable: % rubric criteria are read-only', OLD.status
      USING ERRCODE = 'P0001';
  END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION writing_submissions_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status = 'submitted' THEN
    RAISE EXCEPTION 'submission_immutable: a submitted response cannot change'
      USING ERRCODE = 'P0001';
  END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION sample_answers_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_status text;
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    SELECT tv.status INTO v_status FROM test_versions tv JOIN test_modules tm
      ON tm.test_version_id = tv.id
      LEFT JOIN writing_tasks wt ON wt.test_module_id = tm.id AND wt.id = OLD.writing_task_id
      LEFT JOIN speaking_parts sp ON sp.test_module_id = tm.id AND sp.id = OLD.speaking_part_id
      WHERE wt.id IS NOT NULL OR sp.id IS NOT NULL;
    IF v_status IN ('published', 'archived') THEN
      RAISE EXCEPTION 'content_version_immutable: model answer of a % version', v_status
        USING ERRCODE = 'P0001';
    END IF;
  END IF;
  IF TG_OP IN ('INSERT', 'UPDATE') THEN
    SELECT tv.status INTO v_status FROM test_versions tv JOIN test_modules tm
      ON tm.test_version_id = tv.id
      LEFT JOIN writing_tasks wt ON wt.test_module_id = tm.id AND wt.id = NEW.writing_task_id
      LEFT JOIN speaking_parts sp ON sp.test_module_id = tm.id AND sp.id = NEW.speaking_part_id
      WHERE wt.id IS NOT NULL OR sp.id IS NOT NULL;
    IF v_status IN ('published', 'archived') THEN
      RAISE EXCEPTION 'content_version_immutable: model answer of a % version', v_status
        USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
  END IF;
  RETURN OLD;
END $$;
"""


def upgrade() -> None:
    op.create_table(
        "rubric_versions",
        sa.Column("module", sa.String(length=20), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "criteria", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "module IN ('writing', 'speaking')", name=op.f("ck_rubric_versions_module")
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'in_review', 'published', 'archived')",
            name=op.f("ck_rubric_versions_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rubric_versions")),
        sa.UniqueConstraint(
            "module", "version_no", name=op.f("uq_rubric_versions_module_version_no")
        ),
    )
    op.create_index(
        "uq_rubric_versions_one_published",
        "rubric_versions",
        ["module"],
        unique=True,
        postgresql_where=sa.text("status = 'published'"),
    )
    op.create_table(
        "rubric_reviews",
        sa.Column("rubric_version_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=30), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "decision IN ('approved', 'changes_requested')", name=op.f("ck_rubric_reviews_decision")
        ),
        sa.ForeignKeyConstraint(
            ["rubric_version_id"],
            ["rubric_versions.id"],
            name=op.f("fk_rubric_reviews_rubric_version_id_rubric_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rubric_reviews")),
    )
    op.create_table(
        "speaking_sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("test_version_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="recording", nullable=False),
        sa.Column("processing_consent_id", sa.Uuid(), nullable=False),
        sa.Column("recording_consent_id", sa.Uuid(), nullable=False),
        sa.Column("submit_key", sa.Uuid(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("audio_purge_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "mode IN ('full', 'part1', 'part2', 'part3')", name=op.f("ck_speaking_sessions_mode")
        ),
        sa.CheckConstraint(
            "status IN ('recording', 'submitted')", name=op.f("ck_speaking_sessions_status")
        ),
        sa.ForeignKeyConstraint(
            ["processing_consent_id"],
            ["user_consents.id"],
            name=op.f("fk_speaking_sessions_processing_consent_id_user_consents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recording_consent_id"],
            ["user_consents.id"],
            name=op.f("fk_speaking_sessions_recording_consent_id_user_consents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["test_version_id"],
            ["test_versions.id"],
            name=op.f("fk_speaking_sessions_test_version_id_test_versions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_speaking_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_speaking_sessions")),
        sa.UniqueConstraint("submit_key", name=op.f("uq_speaking_sessions_submit_key")),
    )
    op.create_index(
        "ix_speaking_sessions_user_created",
        "speaking_sessions",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "speaking_evaluations",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("band_fc", sa.Numeric(precision=2, scale=1), nullable=True),
        sa.Column("band_lr", sa.Numeric(precision=2, scale=1), nullable=True),
        sa.Column("band_gra", sa.Numeric(precision=2, scale=1), nullable=True),
        sa.Column("band_pr", sa.Numeric(precision=2, scale=1), nullable=True),
        sa.Column("band_overall", sa.Numeric(precision=2, scale=1), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rubric_version_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=60), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=40), nullable=True),
        sa.Column("prompt_hash", sa.String(length=64), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'unavailable', 'rejected_input')",
            name=op.f("ck_speaking_evaluations_status"),
        ),
        sa.CheckConstraint(
            "band_fc IS NULL OR (band_fc >= 0 AND band_fc <= 9 AND band_fc * 2 = floor(band_fc * 2))",
            name=op.f("ck_speaking_evaluations_band_fc_half_steps"),
        ),
        sa.CheckConstraint(
            "band_gra IS NULL OR (band_gra >= 0 AND band_gra <= 9 AND band_gra * 2 = floor(band_gra * 2))",
            name=op.f("ck_speaking_evaluations_band_gra_half_steps"),
        ),
        sa.CheckConstraint(
            "band_lr IS NULL OR (band_lr >= 0 AND band_lr <= 9 AND band_lr * 2 = floor(band_lr * 2))",
            name=op.f("ck_speaking_evaluations_band_lr_half_steps"),
        ),
        sa.CheckConstraint(
            "band_overall IS NULL OR (band_overall >= 0 AND band_overall <= 9 AND band_overall * 2 = floor(band_overall * 2))",
            name=op.f("ck_speaking_evaluations_band_overall_half_steps"),
        ),
        sa.CheckConstraint(
            "band_pr IS NULL OR (band_pr >= 0 AND band_pr <= 9 AND band_pr * 2 = floor(band_pr * 2))",
            name=op.f("ck_speaking_evaluations_band_pr_half_steps"),
        ),
        sa.ForeignKeyConstraint(
            ["rubric_version_id"],
            ["rubric_versions.id"],
            name=op.f("fk_speaking_evaluations_rubric_version_id_rubric_versions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["speaking_sessions.id"],
            name=op.f("fk_speaking_evaluations_session_id_speaking_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_speaking_evaluations")),
        sa.UniqueConstraint(
            "idempotency_key", name=op.f("uq_speaking_evaluations_idempotency_key")
        ),
    )
    op.create_index(
        "ix_speaking_evaluations_session",
        "speaking_evaluations",
        ["session_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "speaking_recordings",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("part_no", sa.Integer(), nullable=False),
        sa.Column("question_no", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="uploading", nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('uploading', 'ready', 'failed', 'purged')",
            name=op.f("ck_speaking_recordings_status"),
        ),
        sa.CheckConstraint(
            "duration_ms > 0 AND duration_ms <= 900000",
            name=op.f("ck_speaking_recordings_duration"),
        ),
        sa.CheckConstraint("part_no IN (1, 2, 3)", name=op.f("ck_speaking_recordings_part_no")),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["speaking_sessions.id"],
            name=op.f("fk_speaking_recordings_session_id_speaking_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_speaking_recordings")),
        sa.UniqueConstraint(
            "session_id",
            "part_no",
            "question_no",
            name=op.f("uq_speaking_recordings_session_id_part_no_question_no"),
        ),
        sa.UniqueConstraint("storage_key", name=op.f("uq_speaking_recordings_storage_key")),
    )
    op.create_table(
        "writing_submissions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("test_version_id", sa.Uuid(), nullable=False),
        sa.Column("writing_task_id", sa.Uuid(), nullable=False),
        sa.Column("task_no", sa.Integer(), nullable=False),
        sa.Column("prompt_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        sa.Column("word_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("client_revision", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("time_spent_seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("submit_key", sa.Uuid(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'submitted')", name=op.f("ck_writing_submissions_status")
        ),
        sa.CheckConstraint(
            "char_length(body) <= 20000", name=op.f("ck_writing_submissions_body_length")
        ),
        sa.CheckConstraint("task_no IN (1, 2)", name=op.f("ck_writing_submissions_task_no")),
        sa.ForeignKeyConstraint(
            ["test_version_id"],
            ["test_versions.id"],
            name=op.f("fk_writing_submissions_test_version_id_test_versions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_writing_submissions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["writing_task_id"],
            ["writing_tasks.id"],
            name=op.f("fk_writing_submissions_writing_task_id_writing_tasks"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_writing_submissions")),
        sa.UniqueConstraint("submit_key", name=op.f("uq_writing_submissions_submit_key")),
    )
    op.create_index(
        "ix_writing_submissions_user_created",
        "writing_submissions",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_writing_submissions_one_draft",
        "writing_submissions",
        ["user_id", "writing_task_id"],
        unique=True,
        postgresql_where=sa.text("status = 'draft'"),
    )
    op.create_table(
        "writing_evaluations",
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("band_task", sa.Numeric(precision=2, scale=1), nullable=True),
        sa.Column("band_cc", sa.Numeric(precision=2, scale=1), nullable=True),
        sa.Column("band_lr", sa.Numeric(precision=2, scale=1), nullable=True),
        sa.Column("band_gra", sa.Numeric(precision=2, scale=1), nullable=True),
        sa.Column("band_overall", sa.Numeric(precision=2, scale=1), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rubric_version_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=60), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=40), nullable=True),
        sa.Column("prompt_hash", sa.String(length=64), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'unavailable', 'rejected_input')",
            name=op.f("ck_writing_evaluations_status"),
        ),
        sa.CheckConstraint(
            "band_cc IS NULL OR (band_cc >= 0 AND band_cc <= 9 AND band_cc * 2 = floor(band_cc * 2))",
            name=op.f("ck_writing_evaluations_band_cc_half_steps"),
        ),
        sa.CheckConstraint(
            "band_gra IS NULL OR (band_gra >= 0 AND band_gra <= 9 AND band_gra * 2 = floor(band_gra * 2))",
            name=op.f("ck_writing_evaluations_band_gra_half_steps"),
        ),
        sa.CheckConstraint(
            "band_lr IS NULL OR (band_lr >= 0 AND band_lr <= 9 AND band_lr * 2 = floor(band_lr * 2))",
            name=op.f("ck_writing_evaluations_band_lr_half_steps"),
        ),
        sa.CheckConstraint(
            "band_overall IS NULL OR (band_overall >= 0 AND band_overall <= 9 AND band_overall * 2 = floor(band_overall * 2))",
            name=op.f("ck_writing_evaluations_band_overall_half_steps"),
        ),
        sa.CheckConstraint(
            "band_task IS NULL OR (band_task >= 0 AND band_task <= 9 AND band_task * 2 = floor(band_task * 2))",
            name=op.f("ck_writing_evaluations_band_task_half_steps"),
        ),
        sa.ForeignKeyConstraint(
            ["rubric_version_id"],
            ["rubric_versions.id"],
            name=op.f("fk_writing_evaluations_rubric_version_id_rubric_versions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["writing_submissions.id"],
            name=op.f("fk_writing_evaluations_submission_id_writing_submissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_writing_evaluations")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_writing_evaluations_idempotency_key")),
    )
    op.create_index(
        "ix_writing_evaluations_submission",
        "writing_evaluations",
        ["submission_id", "created_at"],
        unique=False,
    )

    # asyncpg runs one statement per execute: each function separately.
    for statement in GUARDS.strip().split("\n\nCREATE "):
        op.execute(statement if statement.startswith("CREATE ") else "CREATE " + statement)
    op.execute(
        "CREATE TRIGGER trg_rubric_versions_guard BEFORE UPDATE OR DELETE ON rubric_versions "
        "FOR EACH ROW EXECUTE FUNCTION rubric_versions_guard()"
    )
    op.execute(
        "CREATE TRIGGER trg_writing_submissions_guard BEFORE UPDATE ON writing_submissions "
        "FOR EACH ROW EXECUTE FUNCTION writing_submissions_guard()"
    )
    op.execute(
        "CREATE TRIGGER trg_sample_answers_guard BEFORE INSERT OR UPDATE OR DELETE ON "
        "sample_answers FOR EACH ROW EXECUTE FUNCTION sample_answers_guard()"
    )


def downgrade() -> None:

    op.execute("DROP TRIGGER IF EXISTS trg_sample_answers_guard ON sample_answers")
    op.execute("DROP TRIGGER IF EXISTS trg_writing_submissions_guard ON writing_submissions")
    op.execute("DROP TRIGGER IF EXISTS trg_rubric_versions_guard ON rubric_versions")
    op.execute("DROP FUNCTION IF EXISTS sample_answers_guard()")
    op.execute("DROP FUNCTION IF EXISTS writing_submissions_guard()")
    op.execute("DROP FUNCTION IF EXISTS rubric_versions_guard()")
    op.drop_index("ix_writing_evaluations_submission", table_name="writing_evaluations")
    op.drop_table("writing_evaluations")
    op.drop_index(
        "uq_writing_submissions_one_draft",
        table_name="writing_submissions",
        postgresql_where=sa.text("status = 'draft'"),
    )
    op.drop_index("ix_writing_submissions_user_created", table_name="writing_submissions")
    op.drop_table("writing_submissions")
    op.drop_table("speaking_recordings")
    op.drop_index("ix_speaking_evaluations_session", table_name="speaking_evaluations")
    op.drop_table("speaking_evaluations")
    op.drop_index("ix_speaking_sessions_user_created", table_name="speaking_sessions")
    op.drop_table("speaking_sessions")
    op.drop_table("rubric_reviews")
    op.drop_index(
        "uq_rubric_versions_one_published",
        table_name="rubric_versions",
        postgresql_where=sa.text("status = 'published'"),
    )
    op.drop_table("rubric_versions")
