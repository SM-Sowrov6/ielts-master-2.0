"""Speaking practice sessions, recordings and AI evaluations (docs/DATABASE_SCHEMA.md §6).

Recordings are uploaded by the browser straight to private object storage (presigned PUT) and
verified server-side (size, signature, SHA-256) before they count. A session needs both the
voice-processing and audio-recording consents (ids are required columns).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.shared.evaluation import EVAL_STATUS, EvaluationMixin, band_check


class SessionStatus(StrEnum):
    RECORDING = "recording"  # recorded practice: answering
    SUBMITTED = "submitted"  # recorded practice: handed in
    CREATED = "created"  # room: set up, candidate in the waiting room
    LIVE = "live"  # room: conversation in progress
    COMPLETED = "completed"  # room: ended (finished or ended by the candidate)


class SessionKind(StrEnum):
    RECORDED = "recorded"  # question-by-question recorder (no examiner)
    ROOM = "room"  # AI Speaking Room with an examiner profile and a frozen configuration


class RecordingStatus(StrEnum):
    UPLOADING = "uploading"
    READY = "ready"
    FAILED = "failed"
    PURGED = "purged"


class SpeakingSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_sessions"
    __table_args__ = (
        CheckConstraint("mode IN ('full', 'part1', 'part2', 'part3')", name="mode"),
        CheckConstraint(
            "status IN ('recording', 'submitted', 'created', 'live', 'completed')", name="status"
        ),
        CheckConstraint("kind IN ('recorded', 'room')", name="kind"),
        CheckConstraint(
            "kind = 'recorded' OR (examiner_id IS NOT NULL AND examiner_config_id IS NOT NULL)",
            name="room_has_examiner",
        ),
        Index("ix_speaking_sessions_user_created", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    test_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_versions.id", ondelete="RESTRICT")
    )
    mode: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), server_default=SessionStatus.RECORDING.value)
    processing_consent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_consents.id", ondelete="RESTRICT")
    )
    recording_consent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_consents.id", ondelete="RESTRICT")
    )
    submit_key: Mapped[uuid.UUID | None] = mapped_column(unique=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    audio_purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # AI Speaking Room (kind = 'room')
    kind: Mapped[str] = mapped_column(String(10), server_default=SessionKind.RECORDED.value)
    room_code: Mapped[str | None] = mapped_column(String(40), unique=True)
    examiner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("examiner_profiles.id", ondelete="RESTRICT")
    )
    examiner_config_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("examiner_configs.id", ondelete="RESTRICT")
    )
    # Frozen at creation: examiner, instructions, timing and the step plan the room follows.
    config_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    conduct_mode: Mapped[str | None] = mapped_column(String(10))  # guided | live
    current_step: Mapped[int] = mapped_column(Integer, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None]
    completion_reason: Mapped[str | None] = mapped_column(String(30))


class SpeakingRecording(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_recordings"
    __table_args__ = (
        CheckConstraint("status IN ('uploading', 'ready', 'failed', 'purged')", name="status"),
        CheckConstraint("part_no IN (1, 2, 3)", name="part_no"),
        CheckConstraint("duration_ms > 0 AND duration_ms <= 900000", name="duration"),
        UniqueConstraint("session_id", "part_no", "question_no"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("speaking_sessions.id", ondelete="CASCADE")
    )
    part_no: Mapped[int]
    question_no: Mapped[int]
    question_text: Mapped[str] = mapped_column(Text)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int | None]
    sha256: Mapped[str] = mapped_column(String(64))
    duration_ms: Mapped[int]
    status: Mapped[str] = mapped_column(String(20), server_default=RecordingStatus.UPLOADING.value)
    transcript: Mapped[str | None] = mapped_column(Text)


class SpeakingEvaluation(UUIDPrimaryKeyMixin, EvaluationMixin, Base):
    __tablename__ = "speaking_evaluations"
    __table_args__ = (
        CheckConstraint(EVAL_STATUS, name="status"),
        band_check("band_fc"),
        band_check("band_lr"),
        band_check("band_gra"),
        band_check("band_pr"),
        band_check("band_overall"),
        Index("ix_speaking_evaluations_session", "session_id", "created_at"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("speaking_sessions.id", ondelete="CASCADE")
    )
    band_fc: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    band_lr: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    band_gra: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    band_pr: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    band_overall: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))


class ExaminerProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A configurable AI examiner persona. `voice` holds provider-independent voice settings for
    the future voice integration (empty until a provider is configured)."""

    __tablename__ = "examiner_profiles"
    __table_args__ = (
        CheckConstraint(
            "difficulty IN ('supportive', 'standard', 'challenging')", name="difficulty"
        ),
    )

    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(120))
    personality: Mapped[str] = mapped_column(Text)
    speaking_style: Mapped[str] = mapped_column(Text)
    accent: Mapped[str | None] = mapped_column(String(80))
    difficulty: Mapped[str] = mapped_column(String(20))
    avatar_tone: Mapped[str] = mapped_column(String(20), server_default="primary")
    voice: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")


class ExaminerConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """How the AI examiner conducts one published Speaking test: question selection and order,
    timing, follow-up behaviour, instructions and criteria. Questions are referenced by index into
    the test version's existing parts (no duplicate question store). A published configuration is
    read-only (database trigger); unpublish to edit."""

    __tablename__ = "examiner_configs"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'published', 'unpublished')", name="status"),
        Index("ix_examiner_configs_status", "status"),
    )

    test_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tests.id", ondelete="RESTRICT"))
    test_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_versions.id", ondelete="RESTRICT")
    )
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), server_default="draft")
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID | None]
    published_by: Mapped[uuid.UUID | None]
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SpeakingTurn(UUIDPrimaryKeyMixin, Base):
    """One line of the room transcript (examiner or candidate), ordered by `seq`. Examiner lines
    come only from the frozen configuration (guided mode) or the voice provider's events (live)."""

    __tablename__ = "speaking_turns"
    __table_args__ = (
        CheckConstraint("speaker IN ('examiner', 'candidate', 'system')", name="speaker"),
        CheckConstraint("part_no IS NULL OR part_no IN (1, 2, 3)", name="part_no"),
        UniqueConstraint("session_id", "seq"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("speaking_sessions.id", ondelete="CASCADE")
    )
    seq: Mapped[int]
    speaker: Mapped[str] = mapped_column(String(10))
    part_no: Mapped[int | None]
    step: Mapped[int | None]
    text: Mapped[str] = mapped_column(Text)
    offset_ms: Mapped[int | None]
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sql_text("now()"), nullable=False
    )
