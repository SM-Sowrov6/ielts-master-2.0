"""Admin console endpoints (docs/API_SPECIFICATION.md §10).

Every route depends on `require_staff_permission`, which re-reads the session, roles and
permissions from the database on each request: 401 without a live session, 403 for a signed-in
account that is not staff, lacks the permission, or (where required) has not passed staff 2FA.
Responses are `Cache-Control: no-store`. These routes are read-only, so no audit entries are
written; every mutating admin route added later must audit its change.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.errors import PROBLEM_MEDIA_TYPE
from app.modules.admin.schemas import (
    AuditActor,
    AuditEntryResponse,
    AuditLogPage,
    ContentOverviewResponse,
    UsersOverviewResponse,
)
from app.modules.audit import api as audit
from app.modules.content import api as content
from app.modules.identity import api as identity

# Any of these lets a staff member see catalogue counts (content managers, reviewers, admins).
CONTENT_READERS = ("content.edit", "content.review", "content.publish")


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


_DENIED: dict[int | str, dict[str, object]] = {
    401: {"description": "Not signed in", "content": {PROBLEM_MEDIA_TYPE: {}}},
    403: {
        "description": "Not staff, missing permission, or two-factor required",
        "content": {PROBLEM_MEDIA_TYPE: {}},
    },
}

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(_no_store)],
    responses=_DENIED,
)

Db = Annotated[AsyncSession, Depends(get_db_session)]


@router.get(
    "/overview/users",
    response_model=UsersOverviewResponse,
    summary="Account counts by status and role",
    dependencies=[Depends(identity.require_staff_permission("users.read"))],
)
async def users_overview(db: Db) -> UsersOverviewResponse:
    async with db.begin():
        data = await identity.user_overview(db)
    return UsersOverviewResponse(
        total=data.total,
        by_status=data.by_status,
        students=data.students,
        staff_by_role=data.staff_by_role,
    )


@router.get(
    "/overview/content",
    response_model=ContentOverviewResponse,
    summary="Content catalogue counts",
    dependencies=[Depends(identity.require_staff_permission(*CONTENT_READERS))],
)
async def content_overview(db: Db) -> ContentOverviewResponse:
    async with db.begin():
        data = await content.content_overview(db)
    return ContentOverviewResponse(
        books=data.books,
        tests=data.tests,
        versions_by_status=data.versions_by_status,
        published_modules=data.published_modules,
    )


@router.get(
    "/audit-logs",
    response_model=AuditLogPage,
    summary="Most recent audit entries (redacted: no IP, no change payload)",
    dependencies=[Depends(identity.require_staff_permission("audit.read"))],
)
async def audit_logs(db: Db, limit: Annotated[int, Query(ge=1, le=50)] = 10) -> AuditLogPage:
    async with db.begin():
        entries = await audit.recent(db, limit=limit)
        names = await identity.display_names(
            db, {e.actor_id for e in entries if e.actor_id is not None}
        )
    return AuditLogPage(
        items=[
            AuditEntryResponse(
                id=e.id,
                created_at=e.created_at,
                action=e.action,
                entity_type=e.entity_type,
                entity_id=e.entity_id,
                actor=AuditActor(id=e.actor_id, name=names.get(e.actor_id))
                if e.actor_id is not None
                else None,
            )
            for e in entries
        ]
    )
