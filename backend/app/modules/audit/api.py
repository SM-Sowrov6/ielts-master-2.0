"""Public interface of the audit module. Every module may call `record` (universal dependency).
`recent` is the read side for the admin console (callers enforce `audit.read`).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog


async def record(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    changes: dict[str, Any] | None = None,
    request_id: str | None = None,
    ip: str | None = None,
) -> None:
    """Append an audit entry inside the caller's transaction (no commit here).

    `changes` must already be redacted: never pass secrets, tokens or personal content.
    `ip` should be a truncated network prefix, not a full address (SECURITY_GUIDELINES.md §11).
    """
    session.add(
        AuditLog(
            actor_user_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes or {},
            request_id=request_id,
            ip=ip,
        )
    )


@dataclass(frozen=True)
class AuditEntry:
    """A redacted view of one audit row for admin screens: no IP prefix, no change payload."""

    id: uuid.UUID
    created_at: datetime
    actor_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: uuid.UUID | None


async def recent(session: AsyncSession, *, limit: int) -> list[AuditEntry]:
    """Newest entries first. Read access must be authorised by the caller (`audit.read`)."""
    rows = await session.execute(
        select(
            AuditLog.id,
            AuditLog.created_at,
            AuditLog.actor_user_id,
            AuditLog.action,
            AuditLog.entity_type,
            AuditLog.entity_id,
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
    )
    return [AuditEntry(*row) for row in rows.all()]
