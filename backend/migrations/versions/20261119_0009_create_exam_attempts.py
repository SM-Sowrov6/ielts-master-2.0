"""Examination engine tables for Listening attempts (docs/EXAMINATION_ENGINE_DESIGN.md).

`exam_templates` (seeded: `listening_only` with the documented practice/exam rules),
`exam_attempts` (writer lease, server deadline, idempotency keys, one open exam-mode attempt per
user+template+version), `attempt_sections` (audio plays), `attempt_answers` (revision-guarded
autosave), `question_scores`, `attempt_results`.

Downgrade refuses to run while attempts exist, so a rollback never silently deletes candidates'
answers or results.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-19
"""

import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# EXAMINATION_ENGINE_DESIGN.md §2.1: exam mode = official timing (30 min + 2 min transfer),
# one play, no seeking, auto-submit at the deadline; practice = timer shown but not enforced,
# replay and seeking allowed. Snapshotted into each attempt at creation.
LISTENING_RULES = {
    "exam": {
        "timing": {"listening_seconds": 1800, "transfer_time_seconds": 120, "enforce": True},
        "navigation": {"free_within_module": True},
        "listening": {"max_plays": 1, "allow_seek": False},
        "feedback": {"instant": False, "show_explanations": "after_completion"},
        "submission": {"auto_submit_on_deadline": True, "grace_seconds": 30},
    },
    "practice": {
        "timing": {"listening_seconds": 1800, "transfer_time_seconds": 120, "enforce": False},
        "navigation": {"free_within_module": True},
        "listening": {"max_plays": None, "allow_seek": True},
        "feedback": {"instant": False, "show_explanations": "after_completion"},
        "submission": {"auto_submit_on_deadline": False, "grace_seconds": 30},
    },
}
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exam_templates",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("exam_type", sa.String(length=30), nullable=False),
        sa.Column("allowed_modes", sa.ARRAY(sa.String(length=20)), nullable=False),
        sa.Column("default_mode", sa.String(length=20), nullable=False),
        sa.Column("rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
            "default_mode IN ('practice', 'exam')", name=op.f("ck_exam_templates_default_mode")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exam_templates")),
        sa.UniqueConstraint("code", name=op.f("uq_exam_templates_code")),
    )
    op.create_table(
        "exam_attempts",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("test_id", sa.Uuid(), nullable=False),
        sa.Column("test_version_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="created", nullable=False),
        sa.Column("config_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_by", sa.String(length=20), nullable=True),
        sa.Column("create_idempotency_key", sa.Uuid(), nullable=True),
        sa.Column("submit_idempotency_key", sa.Uuid(), nullable=True),
        sa.Column("writer_epoch", sa.Integer(), server_default="0", nullable=False),
        sa.Column("writer_token_hash", sa.LargeBinary(length=32), nullable=True),
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
        sa.CheckConstraint("mode IN ('practice', 'exam')", name=op.f("ck_exam_attempts_mode")),
        sa.CheckConstraint(
            "status IN ('created', 'in_progress', 'submitted', 'completed', 'abandoned')",
            name=op.f("ck_exam_attempts_status"),
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["exam_templates.id"],
            name=op.f("fk_exam_attempts_template_id_exam_templates"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["test_id"],
            ["tests.id"],
            name=op.f("fk_exam_attempts_test_id_tests"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["test_version_id"],
            ["test_versions.id"],
            name=op.f("fk_exam_attempts_test_version_id_test_versions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_exam_attempts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exam_attempts")),
        sa.UniqueConstraint("submit_idempotency_key", name="uq_exam_attempts_submit_key"),
        sa.UniqueConstraint(
            "user_id", "create_idempotency_key", name="uq_exam_attempts_user_create_key"
        ),
    )
    op.create_index(
        "ix_exam_attempts_running_deadline",
        "exam_attempts",
        ["deadline_at"],
        unique=False,
        postgresql_where=sa.text("status = 'in_progress' AND deadline_at IS NOT NULL"),
    )
    op.create_index(
        "ix_exam_attempts_user_created", "exam_attempts", ["user_id", "created_at"], unique=False
    )
    op.create_index(
        "uq_exam_attempts_one_open_exam",
        "exam_attempts",
        ["user_id", "template_id", "test_version_id"],
        unique=True,
        postgresql_where=sa.text("mode = 'exam' AND status IN ('created', 'in_progress')"),
    )
    op.create_table(
        "attempt_results",
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("module", sa.String(length=20), nullable=False),
        sa.Column("raw_score", sa.Integer(), nullable=False),
        sa.Column("max_score", sa.Integer(), nullable=False),
        sa.Column("band_estimate", sa.Numeric(precision=2, scale=1), nullable=True),
        sa.Column("band_table_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.String(length=20), server_default="auto", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "raw_score >= 0 AND raw_score <= max_score", name=op.f("ck_attempt_results_raw_range")
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["exam_attempts.id"],
            name=op.f("fk_attempt_results_attempt_id_exam_attempts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attempt_results")),
        sa.UniqueConstraint(
            "attempt_id", "module", name=op.f("uq_attempt_results_attempt_id_module")
        ),
    )
    op.create_table(
        "attempt_sections",
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("section_no", sa.Integer(), nullable=False),
        sa.Column("audio_plays_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("audio_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["exam_attempts.id"],
            name=op.f("fk_attempt_sections_attempt_id_exam_attempts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["sections.id"],
            name=op.f("fk_attempt_sections_section_id_sections"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("attempt_id", "section_id", name=op.f("pk_attempt_sections")),
    )
    op.create_table(
        "attempt_answers",
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("writer_epoch", sa.Integer(), nullable=False),
        sa.Column("client_revision", sa.BigInteger(), nullable=False),
        sa.Column("flagged", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "saved_after_deadline", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "saved_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["exam_attempts.id"],
            name=op.f("fk_attempt_answers_attempt_id_exam_attempts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_attempt_answers_question_id_questions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("attempt_id", "question_id", name=op.f("pk_attempt_answers")),
    )
    op.create_table(
        "question_scores",
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("section_no", sa.Integer(), nullable=False),
        sa.Column("marks_awarded", sa.Integer(), nullable=False),
        sa.Column("marks_available", sa.Integer(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=30), nullable=False),
        sa.Column("question_type", sa.String(length=50), nullable=False),
        sa.Column("scorer_version", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["exam_attempts.id"],
            name=op.f("fk_question_scores_attempt_id_exam_attempts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_question_scores_question_id_questions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("attempt_id", "question_id", name=op.f("pk_question_scores")),
    )
    templates = sa.table(
        "exam_templates",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("exam_type", sa.String()),
        sa.column("allowed_modes", sa.ARRAY(sa.String())),
        sa.column("default_mode", sa.String()),
        sa.column("rules", postgresql.JSONB()),
    )
    op.bulk_insert(
        templates,
        [
            {
                "id": uuid.uuid7(),
                "code": "listening_only",
                "exam_type": "listening",
                "allowed_modes": ["practice", "exam"],
                "default_mode": "practice",
                "rules": json.loads(json.dumps(LISTENING_RULES)),
            }
        ],
    )


def downgrade() -> None:
    attempts = op.get_bind().execute(sa.text("SELECT count(*) FROM exam_attempts")).scalar_one()
    if attempts:
        raise RuntimeError(
            f"Refusing to drop the exam tables: {attempts} attempt(s) exist. "
            "Export or delete them deliberately first."
        )
    op.drop_table("question_scores")
    op.drop_table("attempt_answers")
    op.drop_table("attempt_sections")
    op.drop_table("attempt_results")
    op.drop_index(
        "uq_exam_attempts_one_open_exam",
        table_name="exam_attempts",
        postgresql_where=sa.text("mode = 'exam' AND status IN ('created', 'in_progress')"),
    )
    op.drop_index("ix_exam_attempts_user_created", table_name="exam_attempts")
    op.drop_index(
        "ix_exam_attempts_running_deadline",
        table_name="exam_attempts",
        postgresql_where=sa.text("status = 'in_progress' AND deadline_at IS NOT NULL"),
    )
    op.drop_table("exam_attempts")
    op.drop_table("exam_templates")
