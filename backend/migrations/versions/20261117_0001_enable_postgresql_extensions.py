"""Enable required PostgreSQL extensions: citext, pg_trgm, vector.

- citext: case-insensitive email (users.email)
- pg_trgm: trigram search on titles (books)
- vector: pgvector embeddings (content_chunks)

Requires a role allowed to create these extensions (superuser locally; on managed PostgreSQL the
extensions must be on the provider's allow-list). `IF NOT EXISTS` keeps this safe where an
administrator pre-installed them.

Ownership: extensions are database infrastructure, not application-owned schema. The migration
cannot know whether it or an administrator installed them, so **downgrade never drops them**
(decision 2026-11-17, docs/DATABASE_SCHEMA.md §10). Removing an extension is a manual,
administrator-level operation. Moving creation into provisioning is revisited with D-05.

Revision ID: 0001
Revises:
Create Date: 2026-11-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # Intentionally a no-op: extensions may be admin-owned and shared (see module docstring).
    pass
