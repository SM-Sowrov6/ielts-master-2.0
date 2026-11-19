"""Staff two-factor authentication (TOTP) — SECURITY_GUIDELINES.md §2.

- `user_mfa_factors`: one TOTP factor per user. The shared secret is stored encrypted
  (AES-256-GCM, key derived from AUTH_SECRET_KEY); `confirmed_at` is NULL until the user proves
  the authenticator works; `last_used_step` blocks code replay.
- `user_mfa_recovery_codes`: single-use recovery codes, stored only as keyed hashes.
- `auth_sessions.mfa_verified_at`: set on the session issued after a successful second factor.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_mfa_factors",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("secret_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_step", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "user_mfa_recovery_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.LargeBinary(32), nullable=False, unique=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_user_mfa_recovery_codes_user_id", "user_mfa_recovery_codes", ["user_id"])
    op.add_column(
        "auth_sessions", sa.Column("mfa_verified_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("auth_sessions", "mfa_verified_at")
    op.drop_index("ix_user_mfa_recovery_codes_user_id", table_name="user_mfa_recovery_codes")
    op.drop_table("user_mfa_recovery_codes")
    op.drop_table("user_mfa_factors")
