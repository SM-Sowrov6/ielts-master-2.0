"""Read-only content aggregates for the admin console (exposed through content.api).

Real counts from the content tables; an empty catalogue reports zeros, never sample numbers.
"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.enums import ModuleKind, VersionStatus
from app.modules.content.models import Book, Test, TestModule, TestVersion


@dataclass(frozen=True)
class ContentOverview:
    books: int
    tests: int
    versions_by_status: dict[str, int]
    # Modules contained in currently published versions, by IELTS skill.
    published_modules: dict[str, int]


async def content_overview(session: AsyncSession) -> ContentOverview:
    books = await session.scalar(
        select(func.count()).select_from(Book).where(Book.deleted_at.is_(None))
    )
    tests = await session.scalar(select(func.count()).select_from(Test))
    versions = {status.value: 0 for status in VersionStatus}
    for status, count in (
        await session.execute(select(TestVersion.status, func.count()).group_by(TestVersion.status))
    ).all():
        versions[status] = count
    modules = {kind.value: 0 for kind in ModuleKind}
    for kind, count in (
        await session.execute(
            select(TestModule.module, func.count())
            .join(TestVersion, TestVersion.id == TestModule.test_version_id)
            .where(TestVersion.status == VersionStatus.PUBLISHED.value)
            .group_by(TestModule.module)
        )
    ).all():
        modules[kind] = count
    return ContentOverview(
        books=books or 0,
        tests=tests or 0,
        versions_by_status=versions,
        published_modules=modules,
    )
