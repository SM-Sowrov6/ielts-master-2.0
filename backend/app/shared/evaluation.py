"""Columns and statuses shared by Writing and Speaking AI evaluations (one row per run)."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class EvaluationStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"  # provider/output error after retries (retry allowed)
    UNAVAILABLE = "unavailable"  # no AI provider configured (retry allowed later)
    REJECTED_INPUT = "rejected_input"  # too short/long to assess (never scored)


EVAL_STATUS = (
    "status IN ('queued', 'running', 'succeeded', 'failed', 'unavailable', 'rejected_input')"
)
RETRYABLE = (EvaluationStatus.FAILED.value, EvaluationStatus.UNAVAILABLE.value)


def band_check(column: str) -> CheckConstraint:
    return CheckConstraint(
        f"{column} IS NULL OR "
        f"({column} >= 0 AND {column} <= 9 AND {column} * 2 = floor({column} * 2))",
        name=f"{column}_half_steps",
    )


class EvaluationMixin:
    """Columns shared by writing and speaking evaluations."""

    rubric_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rubric_versions.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(20))
    idempotency_key: Mapped[uuid.UUID] = mapped_column(unique=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(60))
    error_message: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(60))
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    prompt_hash: Mapped[str | None] = mapped_column(String(64))
    attempt_count: Mapped[int] = mapped_column(Integer, server_default="0")
    requested_by: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sql_text("now()"), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
