"""Identity & access schema (docs/DATABASE_SCHEMA.md §3) and RBAC seed data.

Opaque server-side sessions (ADR-006, revised 2026-11-18): `auth_sessions.token_hash` and
`one_time_tokens.token_hash` store SHA-256 hashes only, never raw tokens. Roles and permissions
follow SECURITY_GUIDELINES.md §4.1; `admin.access` gates every staff area.

Downgrade drops the identity tables only while no user account exists, so a rollback can never
silently destroy accounts.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-18
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES: list[tuple[str, str]] = [
    ("super_admin", "Super admin"),
    ("admin", "Admin"),
    ("content_manager", "Content manager"),
    ("reviewer", "Reviewer"),
    ("student", "Student"),
]
STAFF = ["super_admin", "admin", "content_manager", "reviewer"]
SA, AD, CM, RV = "super_admin", "admin", "content_manager", "reviewer"

# (permission code, description, roles granted). Students hold no permissions: their access is
# "authenticated + owns the resource" (SECURITY_GUIDELINES.md §4.2).
PERMISSIONS: list[tuple[str, str, list[str]]] = [
    ("admin.access", "Enter the staff/admin area", STAFF),
    ("users.read", "View user accounts", [SA, AD]),
    ("users.manage", "Suspend, reactivate and edit user accounts", [SA, AD]),
    ("roles.assign", "Assign roles to users", [SA, AD]),
    ("roles.manage", "Change role definitions and permissions", [SA]),
    ("content.edit", "Create and edit content drafts", [SA, AD, CM]),
    ("content.import", "Import content", [SA, AD, CM]),
    ("media.upload", "Upload media", [SA, AD, CM]),
    ("content.review", "Review content versions", [SA, AD, RV]),
    ("content.publish", "Publish and unpublish content", [SA, AD]),
    ("content.licenses.manage", "Manage content licences", [SA, AD]),
    ("exams.configure", "Configure exam templates and band tables", [SA, AD]),
    ("billing.read", "View billing data", [SA, AD]),
    ("billing.manage", "Change billing data", [SA]),
    ("ai.read", "View AI usage and cost", [SA, AD]),
    ("ai.manage", "Change AI provider routing and prompts", [SA]),
    ("speaking.recordings.read", "Access stored speaking recordings", [SA]),
    ("audit.read", "Read the audit log", [SA, AD]),
    ("system.configure", "Change system configuration and feature flags", [SA]),
]


def upgrade() -> None:
    op.create_table(
        "permissions",
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permissions")),
        sa.UniqueConstraint("code", name=op.f("uq_permissions_code")),
    )
    op.create_table(
        "roles",
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("code", name=op.f("uq_roles_code")),
    )
    op.create_table(
        "users",
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('pending', 'active', 'suspended', 'deleted')", name=op.f("ck_users_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=40), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("ip_prefix", postgresql.INET(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_auth_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_auth_sessions_token_hash")),
    )
    op.create_index(
        "ix_auth_sessions_user_id", "auth_sessions", ["user_id", "revoked_at"], unique=False
    )
    op.create_table(
        "one_time_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "purpose IN ('verify_email', 'reset_password')", name=op.f("ck_one_time_tokens_purpose")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_one_time_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_one_time_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_one_time_tokens_token_hash")),
    )
    op.create_index(
        "ix_one_time_tokens_user_purpose", "one_time_tokens", ["user_id", "purpose"], unique=False
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name=op.f("fk_role_permissions_permission_id_permissions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name=op.f("fk_role_permissions_role_id_roles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name=op.f("pk_role_permissions")),
    )
    op.create_table(
        "user_consents",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("consent_type", sa.String(length=30), nullable=False),
        sa.Column("document_version", sa.String(length=50), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "consent_type IN ('terms', 'privacy', 'age_confirmation', 'voice_processing', 'audio_recording', 'marketing', 'parental')",
            name=op.f("ck_user_consents_consent_type"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_consents_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_consents")),
    )
    op.create_index(
        "ix_user_consents_user_type",
        "user_consents",
        ["user_id", "consent_type", "created_at"],
        unique=False,
    )
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.String(length=100), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_profiles")),
    )
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("granted_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], name=op.f("fk_user_roles_role_id_roles"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_roles_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "role_id", name=op.f("pk_user_roles")),
    )
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"], unique=False)

    roles = sa.table("roles", sa.column("id", sa.Uuid()), sa.column("code"), sa.column("name"))
    permissions = sa.table(
        "permissions", sa.column("id", sa.Uuid()), sa.column("code"), sa.column("description")
    )
    role_ids = {code: uuid.uuid7() for code, _ in ROLES}
    permission_ids = {code: uuid.uuid7() for code, _, _ in PERMISSIONS}
    op.bulk_insert(roles, [{"id": role_ids[c], "code": c, "name": n} for c, n in ROLES])
    op.bulk_insert(
        permissions,
        [{"id": permission_ids[c], "code": c, "description": d} for c, d, _ in PERMISSIONS],
    )
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Uuid()),
        sa.column("permission_id", sa.Uuid()),
    )
    op.bulk_insert(
        role_permissions,
        [
            {"role_id": role_ids[role], "permission_id": permission_ids[code]}
            for code, _, granted in PERMISSIONS
            for role in granted
        ],
    )


def downgrade() -> None:
    users = op.get_bind().execute(sa.text("SELECT count(*) FROM users")).scalar_one()
    if users:
        raise RuntimeError(
            f"Refusing to drop the identity schema: {users} user account(s) exist. "
            "Export or delete them deliberately first."
        )
    op.drop_index("ix_user_roles_role_id", table_name="user_roles")
    op.drop_table("user_roles")
    op.drop_table("user_profiles")
    op.drop_index("ix_user_consents_user_type", table_name="user_consents")
    op.drop_table("user_consents")
    op.drop_table("role_permissions")
    op.drop_index("ix_one_time_tokens_user_purpose", table_name="one_time_tokens")
    op.drop_table("one_time_tokens")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("users")
    op.drop_table("roles")
    op.drop_table("permissions")
