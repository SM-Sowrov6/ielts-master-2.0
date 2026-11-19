"""Read-only account aggregates for the admin console (exposed through identity.api).

Counts come straight from the database; nothing is estimated or cached. No personal data is
returned except display names for audit-log actors.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import Role, User, UserProfile, UserRole, UserStatus
from app.modules.identity.provisioning import STAFF_ROLES


@dataclass(frozen=True)
class UserOverview:
    total: int
    by_status: dict[str, int]
    students: int
    staff_by_role: dict[str, int]


async def user_overview(db: AsyncSession) -> UserOverview:
    by_status = {status.value: 0 for status in UserStatus}
    for status, count in (
        await db.execute(select(User.status, func.count()).group_by(User.status))
    ).all():
        by_status[status] = count
    role_counts = {
        code: count
        for code, count in (
            await db.execute(
                select(Role.code, func.count(UserRole.user_id))
                .join(UserRole, UserRole.role_id == Role.id, isouter=True)
                .group_by(Role.code)
            )
        ).all()
    }
    return UserOverview(
        total=sum(by_status.values()),
        by_status=by_status,
        students=role_counts.get("student", 0),
        staff_by_role={role: role_counts.get(role, 0) for role in STAFF_ROLES},
    )


async def display_names(db: AsyncSession, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not user_ids:
        return {}
    rows = await db.execute(
        select(UserProfile.user_id, UserProfile.full_name).where(UserProfile.user_id.in_(user_ids))
    )
    return {user_id: name for user_id, name in rows.all()}
