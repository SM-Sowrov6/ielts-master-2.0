"""Identity & access models (docs/DATABASE_SCHEMA.md §3, SECURITY_GUIDELINES.md §2-4).

Sessions are opaque server-side sessions (ADR-006, revised 2026-11-18): the browser holds a random
256-bit token in an HttpOnly cookie, the database stores only its SHA-256 hash. One-time tokens
(email verification, password reset) are likewise stored only as hashes.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.orm import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserStatus(StrEnum):
    PENDING = "pending"  # registered, email not verified yet: cannot sign in
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class TokenPurpose(StrEnum):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"  # noqa: S105 — enum value, not a credential


class ConsentType(StrEnum):
    TERMS = "terms"
    PRIVACY = "privacy"
    AGE_CONFIRMATION = "age_confirmation"
    VOICE_PROCESSING = "voice_processing"
    AUDIO_RECORDING = "audio_recording"
    MARKETING = "marketing"
    PARENTAL = "parental"


def _check_in(column: str, enum: type[StrEnum]) -> str:
    values = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_check_in("status", UserStatus), name="status"),)

    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), server_default=UserStatus.PENDING.value)
    email_verified_at: Mapped[datetime | None]
    last_login_at: Mapped[datetime | None]
    deleted_at: Mapped[datetime | None]

    profile: Mapped[UserProfile] = relationship(back_populates="user", lazy="raise")


class UserProfile(TimestampMixin, Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    full_name: Mapped[str] = mapped_column(String(100))

    user: Mapped[User] = relationship(back_populates="profile", lazy="raise")


class Role(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))


class Permission(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str] = mapped_column(String(200))


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (Index("ix_user_roles_role_id", "role_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True
    )
    granted_by: Mapped[uuid.UUID | None]  # plain UUID (ADR-016 style): survives grantor deletion
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuthSession(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (Index("ix_auth_sessions_user_id", "user_id", "revoked_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    idle_expires_at: Mapped[datetime]
    absolute_expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    revoked_reason: Mapped[str | None] = mapped_column(String(40))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    # Truncated network prefix only (/24 IPv4, /48 IPv6): data minimisation (SECURITY §11).
    ip_prefix: Mapped[str | None] = mapped_column(INET)
    # Set on a session issued after a successful second factor (staff 2FA, migration 0013).
    mfa_verified_at: Mapped[datetime | None]


class UserMfaFactor(Base):
    """One TOTP factor per user. The secret is AES-GCM encrypted (identity/mfa.py)."""

    __tablename__ = "user_mfa_factors"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    secret_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    confirmed_at: Mapped[datetime | None]
    last_used_step: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserMfaRecoveryCode(UUIDPrimaryKeyMixin, Base):
    """Single-use recovery code, stored only as a keyed hash."""

    __tablename__ = "user_mfa_recovery_codes"
    __table_args__ = (Index("ix_user_mfa_recovery_codes_user_id", "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    code_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    used_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OneTimeToken(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "one_time_tokens"
    __table_args__ = (
        CheckConstraint(_check_in("purpose", TokenPurpose), name="purpose"),
        Index("ix_one_time_tokens_user_purpose", "user_id", "purpose"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime]
    consumed_at: Mapped[datetime | None]  # also set when superseded by a newer token


class UserConsent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "user_consents"
    __table_args__ = (
        CheckConstraint(_check_in("consent_type", ConsentType), name="consent_type"),
        Index("ix_user_consents_user_type", "user_id", "consent_type", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    consent_type: Mapped[str] = mapped_column(String(30))
    document_version: Mapped[str] = mapped_column(String(50))
    granted: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
