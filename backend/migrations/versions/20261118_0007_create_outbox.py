"""Transactional outbox table (ADR-017; app/core/outbox.py documents delivery semantics).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox_messages",
        sa.Column("topic", sa.String(length=80), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
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
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'skipped', 'dead')",
            name=op.f("ck_outbox_messages_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_messages")),
    )
    op.create_index(
        "ix_outbox_messages_due",
        "outbox_messages",
        ["next_attempt_at"],
        unique=False,
        postgresql_where="status = 'pending'",
    )
    op.create_index(
        "ix_outbox_messages_status_updated",
        "outbox_messages",
        ["status", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    pending = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM outbox_messages WHERE status = 'pending'"))
        .scalar_one()
    )
    if pending:
        raise RuntimeError(f"Refusing to drop the outbox: {pending} undelivered message(s).")
    op.drop_index("ix_outbox_messages_status_updated", table_name="outbox_messages")
    op.drop_index(
        "ix_outbox_messages_due",
        table_name="outbox_messages",
        postgresql_where="status = 'pending'",
    )
    op.drop_table("outbox_messages")
