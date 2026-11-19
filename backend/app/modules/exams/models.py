"""Examination engine tables (docs/DATABASE_SCHEMA.md §5, EXAMINATION_ENGINE_DESIGN.md).

Delivered for Listening (2026-11-19). Content is referenced by id (test version, sections,
questions); the exams module reads content only through content.api.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AttemptStatus(StrEnum):
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class AttemptMode(StrEnum):
    PRACTICE = "practice"
    EXAM = "exam"


OPEN_STATUSES = (AttemptStatus.CREATED.value, AttemptStatus.IN_PROGRESS.value)


def _check_in(column: str, enum: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(repr(m.value) for m in enum)})"


class ExamTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "exam_templates"
    __table_args__ = (CheckConstraint(_check_in("default_mode", AttemptMode), name="default_mode"),)

    code: Mapped[str] = mapped_column(String(50), unique=True)
    exam_type: Mapped[str] = mapped_column(String(30))
    allowed_modes: Mapped[list[str]] = mapped_column(ARRAY(String(20)))
    default_mode: Mapped[str] = mapped_column(String(20))
    rules: Mapped[dict[str, Any]] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("true"))


class ExamAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "exam_attempts"
    __table_args__ = (
        CheckConstraint(_check_in("status", AttemptStatus), name="status"),
        CheckConstraint(_check_in("mode", AttemptMode), name="mode"),
        UniqueConstraint(
            "user_id", "create_idempotency_key", name="uq_exam_attempts_user_create_key"
        ),
        UniqueConstraint("submit_idempotency_key", name="uq_exam_attempts_submit_key"),
        Index("ix_exam_attempts_user_created", "user_id", "created_at"),
        # One open exam-mode attempt per (user, template, version) (EXAMINATION_ENGINE_DESIGN §9).
        Index(
            "uq_exam_attempts_one_open_exam",
            "user_id",
            "template_id",
            "test_version_id",
            unique=True,
            postgresql_where=sql_text("mode = 'exam' AND status IN ('created', 'in_progress')"),
        ),
        # Expiry sweeper scans only running attempts with a deadline.
        Index(
            "ix_exam_attempts_running_deadline",
            "deadline_at",
            postgresql_where=sql_text("status = 'in_progress' AND deadline_at IS NOT NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_templates.id", ondelete="RESTRICT")
    )
    test_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tests.id", ondelete="RESTRICT"))
    test_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_versions.id", ondelete="RESTRICT")
    )
    mode: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), server_default=AttemptStatus.CREATED.value)
    # Resolved rules + item manifest, frozen at creation (template edits never affect it).
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by: Mapped[str | None] = mapped_column(String(20))  # candidate | deadline
    create_idempotency_key: Mapped[uuid.UUID | None]
    submit_idempotency_key: Mapped[uuid.UUID | None]
    writer_epoch: Mapped[int] = mapped_column(Integer, server_default="0")
    writer_token_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32))


class AttemptSection(Base):
    __tablename__ = "attempt_sections"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_attempts.id", ondelete="CASCADE"), primary_key=True
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sections.id", ondelete="RESTRICT"), primary_key=True
    )
    section_no: Mapped[int]
    audio_plays_used: Mapped[int] = mapped_column(Integer, server_default="0")
    audio_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AttemptAnswer(Base):
    __tablename__ = "attempt_answers"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_attempts.id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), primary_key=True
    )
    response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # null = cleared
    writer_epoch: Mapped[int]
    client_revision: Mapped[int] = mapped_column(BigInteger)
    flagged: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("false"))
    saved_after_deadline: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("false"))
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class QuestionScore(Base):
    __tablename__ = "question_scores"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_attempts.id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), primary_key=True
    )
    section_no: Mapped[int]
    marks_awarded: Mapped[int]
    marks_available: Mapped[int]
    is_correct: Mapped[bool]
    reason: Mapped[str] = mapped_column(String(30))
    question_type: Mapped[str] = mapped_column(String(50))  # denormalised for analytics
    scorer_version: Mapped[str] = mapped_column(String(20))


class AttemptResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "attempt_results"
    __table_args__ = (
        UniqueConstraint("attempt_id", "module"),
        CheckConstraint("raw_score >= 0 AND raw_score <= max_score", name="raw_range"),
    )

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_attempts.id", ondelete="CASCADE")
    )
    module: Mapped[str] = mapped_column(String(20))
    raw_score: Mapped[int]
    max_score: Mapped[int]
    band_estimate: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    band_table_id: Mapped[uuid.UUID | None]  # plain UUID: a result outlives table edits
    source: Mapped[str] = mapped_column(String(20), server_default="auto")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
