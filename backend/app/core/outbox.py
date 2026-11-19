"""Transactional outbox (ADR-017): durable side effects written in the same transaction as the
state change that causes them, delivered at-least-once by `app.workers.outbox`.

Delivery semantics (docs/SYSTEM_ARCHITECTURE.md §5, SECURITY_GUIDELINES.md §2):
- A row is claimed with `FOR UPDATE SKIP LOCKED` and a lease (`locked_until`). A crashed worker's
  claim expires and the row is retried; concurrent workers never process the same row at once.
- Each claim increments `attempts`; completion is fenced on that value, so only the current
  claimer can mark a row done.
- Delivery is at-least-once: if the side effect succeeds but the completion write fails, the row
  is processed again. Handlers must be safe to repeat (emails carry a stable Message-ID).
- `payload` must never contain secrets in clear text. Rows are cleared (`payload = {}`) once
  terminal and deleted by the cleanup job after their retention window.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import Settings
from app.core.email import EmailSender
from app.core.orm import Base, UUIDPrimaryKeyMixin
from app.shared.ids import new_id


class OutboxStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    SKIPPED = "skipped"  # no longer applicable (e.g. its token was superseded or consumed)
    DEAD = "dead"  # gave up after max attempts


class OutboxMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "outbox_messages"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'sent', 'skipped', 'dead')",
            name="status",
        ),
        Index(
            "ix_outbox_messages_due",
            "next_attempt_at",
            postgresql_where="status = 'pending'",
        ),
        Index("ix_outbox_messages_status_updated", "status", "updated_at"),
    )

    topic: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), server_default=OutboxStatus.PENDING.value)
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    locked_until: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    sent_at: Mapped[datetime | None]


HandlerResult = Literal["sent", "skipped"]


@dataclass(frozen=True)
class OutboxContext:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    sender: EmailSender
    message_id: uuid.UUID


# A handler performs one message's side effect. Raise to retry later; return "skipped" when the
# message no longer applies. Handlers must tolerate being called more than once.
OutboxHandler = Callable[[OutboxContext, dict[str, Any]], Awaitable[HandlerResult]]


def enqueue(session: AsyncSession, topic: str, payload: dict[str, Any]) -> uuid.UUID:
    """Add a message inside the caller's transaction (no commit). Returns its id."""
    message = OutboxMessage(id=new_id(), topic=topic, payload=payload)
    session.add(message)
    return message.id
