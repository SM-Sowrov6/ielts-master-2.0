"""Seed the 18 objective IELTS question types (docs/QUESTION_BANK_DESIGN.md §3).

Codes are stable identifiers and are never renamed. `family` selects the handler family in
`app.modules.content.question_types`. Adding a type later means a new migration inserting one row
plus its handler (QUESTION_BANK_DESIGN.md §3).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LR = ["listening", "reading"]
R = ["reading"]
L = ["listening"]

# (code, family, modules). Families: option, multi_option, text, text_or_option.
QUESTION_TYPES: list[tuple[str, str, list[str]]] = [
    ("mcq_single", "option", LR),
    ("mcq_multi", "multi_option", LR),
    ("tfng", "option", R),
    ("ynng", "option", R),
    ("matching_headings", "option", R),
    ("matching_information", "option", R),
    ("matching_features", "option", LR),
    ("matching_sentence_endings", "option", R),
    ("sentence_completion", "text", LR),
    ("summary_completion", "text_or_option", LR),
    ("note_completion", "text", LR),
    ("table_completion", "text", LR),
    ("flowchart_completion", "text_or_option", LR),
    ("form_completion", "text", L),
    ("diagram_labelling", "text_or_option", LR),
    ("map_labelling", "option", L),
    ("plan_labelling", "text_or_option", L),
    ("short_answer", "text", LR),
]

question_types = sa.table(
    "question_types",
    sa.column("code", sa.String),
    sa.column("family", sa.String),
    sa.column("modules", ARRAY(sa.String)),
    sa.column("handler_version", sa.String),
    sa.column("is_active", sa.Boolean),
)


def upgrade() -> None:
    op.bulk_insert(
        question_types,
        [
            {
                "code": code,
                "family": family,
                "modules": modules,
                "handler_version": "1.0.0",
                "is_active": True,
            }
            for code, family, modules in QUESTION_TYPES
        ],
    )


def downgrade() -> None:
    codes = [code for code, _, _ in QUESTION_TYPES]
    op.execute(question_types.delete().where(question_types.c.code.in_(codes)))
