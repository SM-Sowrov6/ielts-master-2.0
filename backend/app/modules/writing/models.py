"""Writing submissions and AI evaluations (docs/DATABASE_SCHEMA.md §6).

Content is referenced by id (test version, writing task); the writing module reads content only
through content.api. A submission is immutable once submitted (database trigger); evaluations are
separate rows so a failed or unavailable run can be retried without touching the submission.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.shared.evaluation import EVAL_STATUS, EvaluationMixin, band_check


class SubmissionStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"


class WritingSubmission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "writing_submissions"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'submitted')", name="status"),
        CheckConstraint("task_no IN (1, 2)", name="task_no"),
        CheckConstraint("char_length(body) <= 20000", name="body_length"),
        Index(
            "uq_writing_submissions_one_draft",
            "user_id",
            "writing_task_id",
            unique=True,
            postgresql_where=sql_text("status = 'draft'"),
        ),
        Index("ix_writing_submissions_user_created", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    test_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_versions.id", ondelete="RESTRICT")
    )
    writing_task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("writing_tasks.id", ondelete="RESTRICT")
    )
    task_no: Mapped[int]
    # Immutable copy of the task as the candidate saw it (title, prompt, min words, kind).
    prompt_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    body: Mapped[str] = mapped_column(Text, server_default="")
    word_count: Mapped[int] = mapped_column(Integer, server_default="0")
    client_revision: Mapped[int] = mapped_column(BigInteger, server_default="0")
    time_spent_seconds: Mapped[int] = mapped_column(Integer, server_default="0")
    status: Mapped[str] = mapped_column(String(20), server_default=SubmissionStatus.DRAFT.value)
    submit_key: Mapped[uuid.UUID | None] = mapped_column(unique=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WritingEvaluation(UUIDPrimaryKeyMixin, EvaluationMixin, Base):
    __tablename__ = "writing_evaluations"
    __table_args__ = (
        CheckConstraint(EVAL_STATUS, name="status"),
        band_check("band_task"),
        band_check("band_cc"),
        band_check("band_lr"),
        band_check("band_gra"),
        band_check("band_overall"),
        Index("ix_writing_evaluations_submission", "submission_id", "created_at"),
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("writing_submissions.id", ondelete="CASCADE")
    )
    band_task: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))  # TA (Task 1) / TR (Task 2)
    band_cc: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    band_lr: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    band_gra: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    band_overall: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
