"""Seed the `reading_only` exam template (docs/EXAMINATION_ENGINE_DESIGN.md §2.1).

Exam mode: 60 minutes, server-enforced, auto-submit at the deadline (30 s grace). Practice: the
timer is a guide only. Reading has no recording, so there are no `listening` rules.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-19
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

READING_RULES = {
    "exam": {
        "timing": {"module_seconds": 3600, "transfer_time_seconds": 0, "enforce": True},
        "navigation": {"free_within_module": True},
        "feedback": {"instant": False, "show_explanations": "after_completion"},
        "submission": {"auto_submit_on_deadline": True, "grace_seconds": 30},
    },
    "practice": {
        "timing": {"module_seconds": 3600, "transfer_time_seconds": 0, "enforce": False},
        "navigation": {"free_within_module": True},
        "feedback": {"instant": False, "show_explanations": "after_completion"},
        "submission": {"auto_submit_on_deadline": False, "grace_seconds": 30},
    },
}


def upgrade() -> None:
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
                "code": "reading_only",
                "exam_type": "reading",
                "allowed_modes": ["practice", "exam"],
                "default_mode": "practice",
                "rules": READING_RULES,
            }
        ],
    )


def downgrade() -> None:
    used = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM exam_attempts a JOIN exam_templates t ON t.id = a.template_id "
                "WHERE t.code = 'reading_only'"
            )
        )
        .scalar_one()
    )
    if used:
        raise RuntimeError(f"Refusing to remove reading_only: {used} attempt(s) use it.")
    op.execute("DELETE FROM exam_templates WHERE code = 'reading_only'")
