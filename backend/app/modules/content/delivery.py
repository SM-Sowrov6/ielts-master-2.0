"""Candidate delivery of published content (exposed through content.api).

The exams module turns published versions into attempts but never sees answer keys:
- `published_listening_*`: catalogue of published Listening tests (no bodies, no keys).
- `listening_manifest`: the ordered question list an attempt pins (ids, numbers, types, marks).
- `score_responses`: scores raw candidate responses with the registry handlers. Keys stay here.
- `review_items`: accepted answers + explanations, for the post-submission review only. The caller
  must have checked that the attempt is finalised and owned by the requester.
- `section_audio`: the asset behind a section's audio, for short-lived presigned delivery.

Only `published` versions are listed or startable; `archived` versions stay readable for attempts
that already pinned them (CONTENT_MANAGEMENT_ARCHITECTURE.md §3).
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.enums import AssetStatus, ModuleKind, ModuleVariant, VersionStatus
from app.modules.content.errors import ContentNotFoundError
from app.modules.content.models import (
    BandConversionRow,
    BandConversionTable,
    Book,
    BookEdition,
    MediaAsset,
    Question,
    QuestionGroup,
    Section,
    Test,
    TestModule,
    TestVersion,
)
from app.modules.content.question_types import get_handler
from app.modules.content.question_types.base import ResponseError
from app.modules.content.service import load_version_tree
from app.modules.content.tree import group_to_dto

LISTENING = ModuleKind.LISTENING.value
OBJECTIVE = (ModuleKind.LISTENING.value, ModuleKind.READING.value)
READABLE = (VersionStatus.PUBLISHED.value, VersionStatus.ARCHIVED.value)


# ------------------------------------------------------------------------------ catalogue
@dataclass(frozen=True)
class PublishedListening:
    test_id: uuid.UUID
    version_id: uuid.UUID
    code: str
    title: str
    description: str | None
    difficulty: str | None
    tags: list[str]
    duration_seconds: int | None
    book_title: str
    edition_label: str
    is_premium: bool
    sections: int
    questions: int
    published_at: datetime | None


def _published_query(module: str = LISTENING) -> Any:
    sections = (
        select(func.count(Section.id))
        .where(Section.test_module_id == TestModule.id)
        .correlate(TestModule)
        .scalar_subquery()
    )
    questions = (
        select(func.coalesce(func.sum(Question.marks), 0))
        .join(QuestionGroup, QuestionGroup.id == Question.group_id)
        .join(Section, Section.id == QuestionGroup.section_id)
        .where(Section.test_module_id == TestModule.id)
        .correlate(TestModule)
        .scalar_subquery()
    )
    return (
        select(
            Test.id,
            TestVersion.id,
            Test.code,
            Test.title,
            TestVersion.description,
            TestVersion.difficulty,
            TestVersion.tags,
            TestModule.duration_seconds,
            Book.title,
            BookEdition.edition_label,
            Book.is_premium,
            sections.label("sections"),
            questions.label("questions"),
            TestVersion.published_at,
        )
        .join(TestVersion, TestVersion.id == Test.current_published_version_id)
        .join(
            TestModule,
            and_(TestModule.test_version_id == TestVersion.id, TestModule.module == module),
        )
        .join(BookEdition, BookEdition.id == Test.edition_id)
        .join(Book, Book.id == BookEdition.book_id)
        .where(TestVersion.status == VersionStatus.PUBLISHED.value, Book.deleted_at.is_(None))
    )


def _row(r: Any) -> PublishedListening:
    return PublishedListening(
        test_id=r[0],
        version_id=r[1],
        code=r[2],
        title=r[3],
        description=r[4],
        difficulty=r[5],
        tags=list(r[6] or []),
        duration_seconds=r[7],
        book_title=r[8],
        edition_label=r[9],
        is_premium=bool(r[10]),
        sections=int(r[11] or 0),
        questions=int(r[12] or 0),
        published_at=r[13],
    )


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def published_listening_tests(
    session: AsyncSession,
    *,
    search: str | None = None,
    difficulty: str | None = None,
    module: str = LISTENING,
) -> list[PublishedListening]:
    query = _published_query(module)
    if search and search.strip():
        pattern = f"%{_escape_like(search.strip())}%"
        query = query.where(
            or_(
                Test.title.ilike(pattern, escape="\\"),
                Book.title.ilike(pattern, escape="\\"),
                Test.code.ilike(pattern, escape="\\"),
            )
        )
    if difficulty:
        query = query.where(TestVersion.difficulty == difficulty)
    rows = await session.execute(query.order_by(TestVersion.published_at.desc(), Test.id))
    return [_row(r) for r in rows.all()]


async def published_listening_test(
    session: AsyncSession, test_id: uuid.UUID, module: str = LISTENING
) -> PublishedListening:
    row = (await session.execute(_published_query(module).where(Test.id == test_id))).one_or_none()
    if row is None:
        raise ContentNotFoundError("This test is not available.")
    return _row(row)


@dataclass(frozen=True)
class SectionSummary:
    section_no: int
    title: str | None
    context: str | None
    questions: int
    number_from: int | None
    number_to: int | None
    question_types: list[str]
    has_audio: bool


async def listening_sections(session: AsyncSession, version_id: uuid.UUID) -> list[SectionSummary]:
    version = await _readable_tree(session, version_id)
    out = []
    for section in _module(version).sections:
        numbers = [
            n for g in section.groups for q in g.questions for n in (q.number_from, q.number_to)
        ]
        out.append(
            SectionSummary(
                section_no=section.section_no,
                title=section.title,
                context=section.context,
                questions=sum(q.marks for g in section.groups for q in g.questions),
                number_from=min(numbers) if numbers else None,
                number_to=max(numbers) if numbers else None,
                question_types=list(dict.fromkeys(g.question_type for g in section.groups)),
                has_audio=section.audio_asset_id is not None,
            )
        )
    return out


# ------------------------------------------------------------------------------ attempts
async def _readable_tree(session: AsyncSession, version_id: uuid.UUID) -> TestVersion:
    version = await load_version_tree(session, version_id)
    if version.status not in READABLE:
        raise ContentNotFoundError("This test is not available.")
    return version


def _module(version: TestVersion) -> TestModule:
    for module in version.modules:
        if module.module in OBJECTIVE:
            return module
    raise ContentNotFoundError("This test has no Listening or Reading module.")


@dataclass(frozen=True)
class ManifestItem:
    question_id: uuid.UUID
    section_id: uuid.UUID
    section_no: int
    question_type: str
    number_from: int
    number_to: int
    marks: int


async def listening_manifest(session: AsyncSession, version_id: uuid.UUID) -> list[ManifestItem]:
    """Ordered questions of a readable version's Listening module (section, group, number)."""
    version = await _readable_tree(session, version_id)
    return [
        ManifestItem(
            question_id=q.id,
            section_id=section.id,
            section_no=section.section_no,
            question_type=group.question_type,
            number_from=q.number_from,
            number_to=q.number_to,
            marks=q.marks,
        )
        for section in _module(version).sections
        for group in section.groups
        for q in group.questions
    ]


async def listening_student_view(session: AsyncSession, version_id: uuid.UUID) -> dict[str, Any]:
    """Key-stripped Listening content of a readable version (what candidates may see)."""
    version = await _readable_tree(session, version_id)
    module = _module(version)
    return {
        "version_id": str(version.id),
        "module": module.module,
        "duration_seconds": module.duration_seconds,
        "sections": [
            {
                "section_no": s.section_no,
                "title": s.title,
                "context": s.context,
                "instructions": s.instructions,
                "has_audio": s.audio_asset_id is not None,
                "passages": [
                    {
                        "title": p.title,
                        "body": p.body,
                        "paragraphs": [
                            {"label": par.label, "text": par.plain_text} for par in p.paragraphs
                        ],
                    }
                    for p in s.passages
                ],
                "groups": [
                    {
                        **get_handler(g.question_type).student_view(group_to_dto(g)),
                        "has_image": g.image_asset_id is not None,
                    }
                    for g in s.groups
                ],
            }
            for s in module.sections
        ],
    }


@dataclass(frozen=True)
class ScoredItem:
    question_id: uuid.UUID
    marks_awarded: int
    marks_available: int
    is_correct: bool
    reason: str
    question_type: str
    scorer_version: str


async def score_responses(
    session: AsyncSession, version_id: uuid.UUID, responses: Mapping[uuid.UUID, Any]
) -> list[ScoredItem]:
    """Score every question of the version (unanswered = 0). Malformed responses score 0."""
    version = await _readable_tree(session, version_id)
    out: list[ScoredItem] = []
    for section in _module(version).sections:
        for group in section.groups:
            handler = get_handler(group.question_type)
            dto = group_to_dto(group)
            for question in dto.questions:
                if question.id is None:  # pragma: no cover - persisted rows always have ids
                    continue
                try:
                    outcome = handler.score(dto, question, responses.get(question.id))
                    awarded, correct, reason = (
                        outcome.marks_awarded,
                        outcome.is_correct,
                        outcome.reason,
                    )
                except ResponseError:
                    awarded, correct, reason = 0, False, "invalid_response"
                out.append(
                    ScoredItem(
                        question_id=question.id,
                        marks_awarded=awarded,
                        marks_available=question.marks,
                        is_correct=correct,
                        reason=reason,
                        question_type=group.question_type,
                        scorer_version=handler.version,
                    )
                )
    return out


@dataclass(frozen=True)
class ReviewItem:
    question_id: uuid.UUID
    accepted: list[list[str]]  # per answer slot: canonical first, then accepted variants
    explanation: dict[str, Any] | None
    evidence_paragraph: str | None = None  # Reading: label of the supporting paragraph


async def review_items(session: AsyncSession, version_id: uuid.UUID) -> list[ReviewItem]:
    """Answer keys and explanations. Only for finalised attempts (checked by the caller)."""
    version = await _readable_tree(session, version_id)
    labels = {
        par.id: par.label
        for section in _module(version).sections
        for passage in section.passages
        for par in passage.paragraphs
    }
    return [
        ReviewItem(
            question_id=q.id,
            accepted=[[k.canonical_value, *(v.value for v in k.variants)] for k in q.answer_keys],
            explanation=q.explanation.body if q.explanation else None,
            evidence_paragraph=labels.get(q.explanation.evidence_paragraph_id)
            if q.explanation and q.explanation.evidence_paragraph_id
            else None,
        )
        for section in _module(version).sections
        for group in section.groups
        for q in group.questions
    ]


@dataclass(frozen=True)
class SectionAudio:
    storage_key: str
    mime_type: str


async def section_audio(
    session: AsyncSession, version_id: uuid.UUID, section_no: int
) -> SectionAudio:
    version = await session.get(TestVersion, version_id)
    if version is None or version.status not in READABLE:
        raise ContentNotFoundError("This test is not available.")
    asset = await session.scalar(
        select(MediaAsset)
        .join(Section, Section.audio_asset_id == MediaAsset.id)
        .join(TestModule, TestModule.id == Section.test_module_id)
        .where(
            TestModule.test_version_id == version_id,
            TestModule.module == LISTENING,
            Section.section_no == section_no,
        )
    )
    if asset is None or asset.status != AssetStatus.READY:
        raise ContentNotFoundError("No audio is available for this section.")
    return SectionAudio(asset.storage_key, asset.mime_type)


async def group_image(
    session: AsyncSession, version_id: uuid.UUID, section_no: int, group_no: int
) -> SectionAudio:
    """The image of the `group_no`-th (1-based) question group of a section (maps, plans)."""
    version = await session.get(TestVersion, version_id)
    if version is None or version.status not in READABLE:
        raise ContentNotFoundError("This test is not available.")
    groups = (
        (
            await session.execute(
                select(QuestionGroup.image_asset_id)
                .join(Section, Section.id == QuestionGroup.section_id)
                .join(TestModule, TestModule.id == Section.test_module_id)
                .where(
                    TestModule.test_version_id == version_id,
                    TestModule.module == LISTENING,
                    Section.section_no == section_no,
                )
                .order_by(QuestionGroup.sort_order)
            )
        )
        .scalars()
        .all()
    )
    asset_id = groups[group_no - 1] if 0 < group_no <= len(groups) else None
    asset = await session.get(MediaAsset, asset_id) if asset_id else None
    if asset is None or asset.status != AssetStatus.READY:
        raise ContentNotFoundError("No image is available for this question group.")
    return SectionAudio(asset.storage_key, asset.mime_type)


@dataclass(frozen=True)
class BandEstimate:
    band: Decimal
    table_id: uuid.UUID
    table_label: str


async def listening_band(
    session: AsyncSession, raw_score: int, module: str = LISTENING
) -> BandEstimate | None:
    """Raw score -> band from the approved default Listening table, or None when no approved
    table exists (none is seeded until a source is approved: no band is ever invented)."""
    row = (
        await session.execute(
            select(BandConversionRow.band, BandConversionTable.id, BandConversionTable.label)
            .join(BandConversionTable, BandConversionTable.id == BandConversionRow.table_id)
            .where(
                BandConversionTable.module == module,
                BandConversionTable.variant
                == (
                    ModuleVariant.COMMON.value
                    if module == LISTENING
                    else ModuleVariant.ACADEMIC.value
                ),
                BandConversionTable.is_default,
                BandConversionRow.raw_min <= raw_score,
                BandConversionRow.raw_max >= raw_score,
            )
        )
    ).one_or_none()
    return BandEstimate(row[0], row[1], row[2]) if row else None


async def test_id_for_version(session: AsyncSession, version_id: uuid.UUID) -> uuid.UUID | None:
    return await session.scalar(select(TestVersion.test_id).where(TestVersion.id == version_id))


async def test_title_for_version(session: AsyncSession, version_id: uuid.UUID) -> str:
    title = await session.scalar(
        select(Test.title)
        .join(TestVersion, TestVersion.test_id == Test.id)
        .where(TestVersion.id == version_id)
    )
    return title or ""
