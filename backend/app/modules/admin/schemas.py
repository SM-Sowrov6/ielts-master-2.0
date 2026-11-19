"""Response schemas for the admin console API."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class UsersOverviewResponse(BaseModel):
    total: int
    by_status: dict[str, int]
    students: int
    staff_by_role: dict[str, int]


class ContentOverviewResponse(BaseModel):
    books: int
    tests: int
    versions_by_status: dict[str, int]
    published_modules: dict[str, int]


class AuditActor(BaseModel):
    id: uuid.UUID
    name: str | None  # None when the account no longer exists


class AuditEntryResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    actor: AuditActor | None  # None: system or operator (CLI) action


class AuditLogPage(BaseModel):
    items: list[AuditEntryResponse]
