"""Admin authoring of Listening tests on top of the existing content domain.

No parallel model: a "Listening test" is a catalogue `Test` whose versions contain a
`listening/common` module. Drafts are edited by replacing that module's section tree with one
built by the import pipeline (`importer.build_sections`), so the import schema, key notation,
handlers and validator are the single source of rules. Workflow (submit, four-eyes review,
publish, archive, new revision) reuses `service`. Every function runs in the caller's
transaction and audits state changes.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Select, and_, case, delete, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit import api as audit
from app.modules.content import service
from app.modules.content.enums import (
    AssetKind,
    Difficulty,
    EditionVariant,
    LicenceSource,
    ModuleKind,
    ModuleVariant,
    ReviewDecision,
    VersionStatus,
)
from app.modules.content.errors import (
    CatalogConflictError,
    ContentNotFoundError,
    ContentStateError,
    ContentValidationError,
    DraftConflictError,
)
from app.modules.content.importer import SectionIn, build_sections
from app.modules.content.models import (
    Book,
    BookEdition,
    ContentLicence,
    ContentReview,
    MediaAsset,
    Question,
    QuestionGroup,
    Section,
    Test,
    TestModule,
    TestVersion,
)
from app.modules.content.question_types import get_handler
from app.modules.content.question_types.base import ValidationIssue, error
from app.modules.content.question_types.catalog import TYPE_MODULES
from app.modules.content.tree import group_to_dto
from app.modules.content.validator import has_errors
from app.shared.ids import new_id

LISTENING = ModuleKind.LISTENING.value
COMMON = ModuleVariant.COMMON.value
LISTENING_TYPES = tuple(code for code, modules in TYPE_MODULES.items() if LISTENING in modules)

# Objective (question-based) modules managed by this editor: kind -> (variant, sections).
# Reading is authored as Academic (General Training reuses the same structure later).
ObjectiveModule = Literal["listening", "reading"]
ContentModule = Literal["listening", "reading", "writing", "speaking"]
OBJECTIVE: dict[str, tuple[str, int]] = {
    ModuleKind.LISTENING.value: (ModuleVariant.COMMON.value, 4),
    ModuleKind.READING.value: (ModuleVariant.ACADEMIC.value, 3),
}


def module_types(module: str) -> tuple[str, ...]:
    return tuple(code for code, modules in TYPE_MODULES.items() if module in modules)


_SLUG = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
_CODE = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,49}$"
_STRICT = ConfigDict(extra="forbid")
Tag = Annotated[str, Field(min_length=1, max_length=50)]

ListStatus = Literal["draft", "in_review", "approved", "published", "archived"]


# ------------------------------------------------------------------------------ inputs
class CreateListeningTestIn(BaseModel):
    model_config = _STRICT
    edition_id: uuid.UUID
    code: str = Field(pattern=_CODE)
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    difficulty: Difficulty | None = None
    tags: list[Tag] = Field(default_factory=list, max_length=20)
    duration_seconds: int | None = Field(default=None, ge=60, le=4 * 3600)
    admin_notes: str | None = Field(default=None, max_length=5000)
    # Writing only: Academic or General Training (decides the Task 1 kind).
    variant: Literal["academic", "general"] | None = None


class SaveListeningDraftIn(BaseModel):
    model_config = _STRICT
    revision: datetime  # the draft's `updated_at` the editor loaded (optimistic concurrency)
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    difficulty: Difficulty | None = None
    tags: list[Tag] = Field(default_factory=list, max_length=20)
    duration_seconds: int | None = Field(default=None, ge=60, le=4 * 3600)
    admin_notes: str | None = Field(default=None, max_length=5000)
    change_note: str | None = Field(default=None, max_length=2000)
    sections: list[SectionIn] = Field(max_length=4)


class DuplicateIn(BaseModel):
    model_config = _STRICT
    code: str = Field(pattern=_CODE)
    title: str = Field(min_length=1, max_length=300)


class LicenceIn(BaseModel):
    model_config = _STRICT
    licensor: str = Field(min_length=1, max_length=200)
    licence_reference: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)


class BookCreateIn(BaseModel):
    model_config = _STRICT
    license_id: uuid.UUID
    slug: str = Field(pattern=_SLUG, max_length=120)
    title: str = Field(min_length=1, max_length=300)
    series: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class EditionCreateIn(BaseModel):
    model_config = _STRICT
    label: str = Field(min_length=1, max_length=100)
    publication_year: int | None = Field(default=None, ge=1980, le=2100)
    variant: EditionVariant = EditionVariant.BOTH


# ------------------------------------------------------------------------------ outputs
@dataclass(frozen=True)
class ListeningRow:
    test_id: uuid.UUID
    version_id: uuid.UUID
    version_no: int
    code: str
    title: str
    book_title: str
    edition_label: str
    status: str  # draft | in_review | approved | published | archived
    difficulty: str | None
    sections: int
    questions: int
    duration_seconds: int | None
    updated_at: datetime
    created_by: uuid.UUID | None
    live_version_id: uuid.UUID | None


@dataclass(frozen=True)
class ListeningPage:
    items: list[ListeningRow]
    total: int


@dataclass(frozen=True)
class ListeningOverview:
    total: int
    by_status: dict[str, int] = field(default_factory=dict)


# ------------------------------------------------------------------------------ listing
def _latest_listening(module: str = LISTENING) -> Select[Any]:
    """One row per test: its latest version, when that version has a listening module."""
    latest = (
        select(TestVersion.test_id, func.max(TestVersion.version_no).label("version_no"))
        .group_by(TestVersion.test_id)
        .subquery()
    )
    approved = exists().where(
        ContentReview.test_version_id == TestVersion.id,
        ContentReview.decision == ReviewDecision.APPROVED.value,
        or_(
            TestVersion.submitted_at.is_(None), ContentReview.created_at >= TestVersion.submitted_at
        ),
        or_(TestVersion.created_by.is_(None), ContentReview.reviewer_id != TestVersion.created_by),
    )
    status = case(
        (and_(TestVersion.status == VersionStatus.IN_REVIEW.value, approved), "approved"),
        else_=TestVersion.status,
    )
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
            Test.id.label("test_id"),
            TestVersion.id.label("version_id"),
            TestVersion.version_no.label("version_no"),
            Test.code.label("code"),
            Test.title.label("title"),
            Book.title.label("book_title"),
            BookEdition.edition_label.label("edition_label"),
            status.label("status"),
            TestVersion.difficulty.label("difficulty"),
            sections.label("sections"),
            questions.label("questions"),
            TestModule.duration_seconds.label("duration_seconds"),
            TestVersion.updated_at.label("updated_at"),
            TestVersion.created_by.label("created_by"),
            Test.current_published_version_id.label("live_version_id"),
        )
        .join(latest, latest.c.test_id == Test.id)
        .join(
            TestVersion,
            and_(TestVersion.test_id == Test.id, TestVersion.version_no == latest.c.version_no),
        )
        .join(
            TestModule,
            and_(
                TestModule.test_version_id == TestVersion.id,
                TestModule.module == module,
            ),
        )
        .join(BookEdition, BookEdition.id == Test.edition_id)
        .join(Book, Book.id == BookEdition.book_id)
    )


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _row(r: Any) -> ListeningRow:
    return ListeningRow(
        test_id=r[0],
        version_id=r[1],
        version_no=r[2],
        code=r[3],
        title=r[4],
        book_title=r[5],
        edition_label=r[6],
        status=r[7],
        difficulty=r[8],
        sections=int(r[9] or 0),
        questions=int(r[10] or 0),
        duration_seconds=r[11],
        updated_at=r[12],
        created_by=r[13],
        live_version_id=r[14],
    )


async def list_listening_tests(
    session: AsyncSession,
    *,
    search: str | None = None,
    status: ListStatus | None = None,
    difficulty: Difficulty | None = None,
    offset: int = 0,
    limit: int = 20,
    module: str = LISTENING,
) -> ListeningPage:
    rows = _latest_listening(module).subquery()
    query = select(rows)
    if search and search.strip():
        pattern = f"%{_escape_like(search.strip())}%"
        query = query.where(
            or_(rows.c.title.ilike(pattern, escape="\\"), rows.c.code.ilike(pattern, escape="\\"))
        )
    if status is not None:
        query = query.where(rows.c.status == status)
    if difficulty is not None:
        query = query.where(rows.c.difficulty == difficulty.value)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    page = await session.execute(
        query.order_by(rows.c.updated_at.desc(), rows.c.version_id.desc())
        .offset(offset)
        .limit(limit)
    )
    return ListeningPage(items=[_row(r) for r in page.all()], total=total or 0)


async def listening_overview(session: AsyncSession, module: str = LISTENING) -> ListeningOverview:
    counts = {s: 0 for s in ("draft", "in_review", "approved", "published", "archived")}
    rows = _latest_listening(module).subquery()
    for status, count in (
        await session.execute(select(rows.c.status, func.count()).group_by(rows.c.status))
    ).all():
        counts[status] = count
    return ListeningOverview(total=sum(counts.values()), by_status=counts)


# ------------------------------------------------------------------------------ catalogue
async def list_licences(session: AsyncSession) -> list[ContentLicence]:
    return list(await session.scalars(select(ContentLicence).order_by(ContentLicence.created_at)))


async def create_original_licence(
    session: AsyncSession, data: LicenceIn, *, actor_id: uuid.UUID
) -> ContentLicence:
    """In-house original content (the only source allowed before D-04 is decided)."""
    licence = ContentLicence(
        source_type=LicenceSource.ORIGINAL.value,
        licensor=data.licensor,
        licence_reference=data.licence_reference,
        notes=data.notes,
    )
    session.add(licence)
    await session.flush()
    await audit.record(
        session,
        actor_id=actor_id,
        action="content.licence.create",
        entity_type="content_licence",
        entity_id=licence.id,
        changes={"source_type": licence.source_type},
    )
    return licence


@dataclass(frozen=True)
class BookWithEditions:
    book: Book
    editions: list[BookEdition]


async def list_books(session: AsyncSession) -> list[BookWithEditions]:
    books = list(
        await session.scalars(select(Book).where(Book.deleted_at.is_(None)).order_by(Book.title))
    )
    editions = list(
        await session.scalars(
            select(BookEdition)
            .where(BookEdition.book_id.in_([b.id for b in books]))
            .order_by(BookEdition.sort_order, BookEdition.edition_label)
        )
    )
    return [BookWithEditions(b, [e for e in editions if e.book_id == b.id]) for b in books]


async def create_book(session: AsyncSession, data: BookCreateIn, *, actor_id: uuid.UUID) -> Book:
    if await session.get(ContentLicence, data.license_id) is None:
        raise ContentNotFoundError(f"Licence {data.license_id} not found.")
    if await session.scalar(select(Book.id).where(Book.slug == data.slug)) is not None:
        raise CatalogConflictError("A book with this slug already exists.")
    book = Book(
        slug=data.slug,
        title=data.title,
        series=data.series,
        description=data.description,
        license_id=data.license_id,
    )
    session.add(book)
    await session.flush()
    await audit.record(
        session,
        actor_id=actor_id,
        action="content.book.create",
        entity_type="book",
        entity_id=book.id,
        changes={"slug": book.slug},
    )
    return book


async def create_edition(
    session: AsyncSession, book_id: uuid.UUID, data: EditionCreateIn, *, actor_id: uuid.UUID
) -> BookEdition:
    if await session.get(Book, book_id) is None:
        raise ContentNotFoundError(f"Book {book_id} not found.")
    duplicate = await session.scalar(
        select(BookEdition.id).where(
            BookEdition.book_id == book_id, BookEdition.edition_label == data.label
        )
    )
    if duplicate is not None:
        raise CatalogConflictError("This book already has an edition with that label.")
    edition = BookEdition(
        book_id=book_id,
        edition_label=data.label,
        publication_year=data.publication_year,
        variant=data.variant.value,
    )
    session.add(edition)
    await session.flush()
    await audit.record(
        session,
        actor_id=actor_id,
        action="content.edition.create",
        entity_type="book_edition",
        entity_id=edition.id,
        changes={"book_id": str(book_id), "label": data.label},
    )
    return edition


# ------------------------------------------------------------------------------ create / edit
async def _code_taken(session: AsyncSession, edition_id: uuid.UUID, code: str) -> bool:
    return (
        await session.scalar(
            select(Test.id).where(
                Test.edition_id == edition_id, func.lower(Test.code) == code.lower()
            )
        )
        is not None
    )


async def create_listening_test(
    session: AsyncSession,
    data: CreateListeningTestIn,
    *,
    actor_id: uuid.UUID,
    module: str = LISTENING,
) -> TestVersion:
    """A new catalogue test with draft v1: one objective module (Listening: 4 empty sections,
    Reading: 3 empty passage sections)."""
    variant, section_count = OBJECTIVE[module]
    if await session.get(BookEdition, data.edition_id) is None:
        raise ContentNotFoundError(f"Edition {data.edition_id} not found.")
    if await _code_taken(session, data.edition_id, data.code):
        raise CatalogConflictError("This edition already has a test with that identifier.")
    test = Test(
        edition_id=data.edition_id,
        code=data.code,
        title=data.title,
        admin_notes=data.admin_notes,
    )
    session.add(test)
    try:
        await session.flush()
    except IntegrityError as exc:  # concurrent create with the same code
        raise CatalogConflictError("This edition already has a test with that identifier.") from exc
    version = TestVersion(
        test_id=test.id,
        version_no=1,
        created_by=actor_id,
        description=data.description,
        difficulty=data.difficulty.value if data.difficulty else None,
        tags=list(data.tags),
        modules=[
            TestModule(
                module=module,
                variant=variant,
                duration_seconds=data.duration_seconds,
                sort_order=0,
                sections=[Section(section_no=n) for n in range(1, section_count + 1)],
            )
        ],
    )
    session.add(version)
    await session.flush()
    await audit.record(
        session,
        actor_id=actor_id,
        action="content.test.create",
        entity_type="test",
        entity_id=test.id,
        changes={"test_version_id": str(version.id), "module": module},
    )
    return version


def _listening_module(version: TestVersion) -> TestModule:
    """The version's objective module (Listening or Reading)."""
    for module in version.modules:
        if module.module in OBJECTIVE:
            return module
    raise ContentStateError("This version has no Listening or Reading module.")


def _where(module: TestModule) -> str:
    return f"{module.module}/{module.variant}"


async def _asset_issues(
    session: AsyncSession,
    sections: list[SectionIn],
    licence_id: uuid.UUID | None,
    where_module: str = "listening/common",
) -> list[ValidationIssue]:
    """Referenced assets must be of the right kind and belong to the test's licence."""
    wanted: dict[uuid.UUID, tuple[str, str]] = {}
    for s in sections:
        if s.audio_asset_id:
            wanted[s.audio_asset_id] = (
                AssetKind.AUDIO.value,
                f"{where_module} > section {s.section_no}",
            )
        for index, g in enumerate(s.groups, start=1):
            if g.image_asset_id:
                where = f"{where_module} > section {s.section_no}"
                wanted[g.image_asset_id] = (
                    AssetKind.IMAGE.value,
                    f"{where} > group {index} ({g.question_type})",
                )
    if not wanted:
        return []
    assets = {
        a.id: a for a in await session.scalars(select(MediaAsset).where(MediaAsset.id.in_(wanted)))
    }
    issues = []
    for asset_id, (kind, location) in wanted.items():
        asset = assets.get(asset_id)
        if asset is None:
            continue  # reported by the validator as asset_not_found
        if asset.kind != kind:
            issues.append(error("asset_kind_mismatch", location, f"Expected an {kind} file."))
        elif licence_id is not None and asset.license_id != licence_id:
            issues.append(
                error("asset_licence_mismatch", location, "The file belongs to another licence.")
            )
    return issues


@dataclass(frozen=True)
class SaveResult:
    version: TestVersion
    issues: list[ValidationIssue]  # publish-strictness findings (what still blocks submission)


async def save_listening_draft(
    session: AsyncSession, version_id: uuid.UUID, data: SaveListeningDraftIn, *, actor_id: uuid.UUID
) -> SaveResult:
    version = await service.load_version_tree(session, version_id)
    if version.status != VersionStatus.DRAFT:
        raise ContentStateError("Only drafts can be edited. Create a new revision instead.")
    if version.updated_at != data.revision:
        raise DraftConflictError()
    test = await session.get_one(Test, version.test_id, with_for_update=True)
    module = _listening_module(version)
    where = _where(module)
    _, max_sections = OBJECTIVE[module.module]
    numbers = [s.section_no for s in data.sections]
    issues: list[ValidationIssue] = []
    if len(numbers) != len(set(numbers)):
        issues.append(error("section_duplicate", where, "Each section number once."))
    for s in data.sections:
        if s.section_no > max_sections:
            issues.append(
                error("section_invalid", f"{where} > section {s.section_no}", "No such section.")
            )
        if module.module == LISTENING and s.passages:
            issues.append(
                error(
                    "passages_not_allowed",
                    f"{where} > section {s.section_no}",
                    "Listening sections have no reading passages.",
                )
            )
        if module.module != LISTENING and s.audio_asset_id:
            issues.append(
                error(
                    "audio_not_allowed",
                    f"{where} > section {s.section_no}",
                    "Reading sections have no recording.",
                )
            )
    licence = await service.licence_for_test(session, version.test_id)
    issues += await _asset_issues(session, data.sections, licence.id if licence else None, where)
    new_sections, build_issues = build_sections(data.sections, module.module, module.variant)
    issues += build_issues
    if data.title != test.title and test.current_published_version_id is not None:
        issues.append(
            error(
                "title_locked",
                "test",
                "The title of a published test cannot change from a draft.",
            )
        )
    if has_errors(issues):
        raise ContentValidationError(issues)

    # Replace the module's section tree (draft rows only; the immutability triggers allow it).
    for section in list(module.sections):
        module.sections.remove(section)
    await session.flush()
    module.sections.extend(sorted(new_sections, key=lambda s: s.section_no))
    module.duration_seconds = data.duration_seconds
    version.description = data.description
    version.difficulty = data.difficulty.value if data.difficulty else None
    version.tags = list(data.tags)
    version.change_note = data.change_note
    version.updated_at = func.now()
    test.title = data.title
    test.admin_notes = data.admin_notes
    await session.flush()

    import_issues = await service.validate_persisted_version(session, version, "import")
    if has_errors(import_issues):
        raise ContentValidationError(import_issues)  # rolled back by the caller
    await session.refresh(version, ["updated_at"])
    await audit.record(
        session,
        actor_id=actor_id,
        action="content.test_version.save_draft",
        entity_type="test_version",
        entity_id=version.id,
        changes={"sections": len(new_sections)},
    )
    reloaded = await service.load_version_tree(session, version.id)
    return SaveResult(
        reloaded, await service.validate_persisted_version(session, reloaded, "publish")
    )


async def validate_for_publish(
    session: AsyncSession, version_id: uuid.UUID
) -> list[ValidationIssue]:
    version = await service.load_version_tree(session, version_id)
    return await service.validate_persisted_version(session, version, "publish")


async def duplicate_test(
    session: AsyncSession, version_id: uuid.UUID, data: DuplicateIn, *, actor_id: uuid.UUID
) -> TestVersion:
    """A new test in the same edition whose draft v1 is a deep copy of `version_id`."""
    source = await service.load_version_tree(session, version_id)
    source_test = await session.get_one(Test, source.test_id)
    if await _code_taken(session, source_test.edition_id, data.code):
        raise CatalogConflictError("This edition already has a test with that identifier.")
    test = Test(edition_id=source_test.edition_id, code=data.code, title=data.title)
    session.add(test)
    await session.flush()
    copy = service.clone_version(source, 1, actor_id)
    copy.test_id = test.id
    copy.change_note = None
    # Duplicates are new tests: their questions get new lineages (no shared history).
    for module in copy.modules:
        for section in module.sections:
            for group in section.groups:
                for question in group.questions:
                    question.lineage_id = new_id()
    session.add(copy)
    await session.flush()
    await audit.record(
        session,
        actor_id=actor_id,
        action="content.test.duplicate",
        entity_type="test",
        entity_id=test.id,
        changes={"source_version_id": str(version_id), "test_version_id": str(copy.id)},
    )
    return copy


async def delete_draft(
    session: AsyncSession, version_id: uuid.UUID, *, actor_id: uuid.UUID
) -> None:
    """Discard a draft. A test whose only version was this draft is removed with it."""
    version = await session.get(TestVersion, version_id)
    if version is None:
        raise ContentNotFoundError(f"Test version {version_id} not found.")
    if version.status != VersionStatus.DRAFT:
        raise ContentStateError("Only drafts can be deleted; published content is archived.")
    test_id = version.test_id
    await session.execute(delete(TestVersion).where(TestVersion.id == version_id))
    remaining = await session.scalar(
        select(func.count()).select_from(TestVersion).where(TestVersion.test_id == test_id)
    )
    if not remaining:
        await session.execute(delete(Test).where(Test.id == test_id))
    await audit.record(
        session,
        actor_id=actor_id,
        action="content.test_version.delete_draft",
        entity_type="test_version",
        entity_id=version_id,
        changes={"test_id": str(test_id), "test_deleted": not remaining},
    )


async def new_revision(
    session: AsyncSession, test_id: uuid.UUID, *, actor_id: uuid.UUID
) -> TestVersion:
    """Edit published content safely: a new draft deep-copied from the live version."""
    return await service.create_next_draft(session, test_id, actor_id=actor_id)


# ------------------------------------------------------------------------------ editor view
def _answers(question: Question) -> list[dict[str, Any]]:
    return [
        {"value": k.notation or k.canonical_value, "slot": k.slot, "match_mode": k.match_mode}
        for k in question.answer_keys
    ]


def section_document(section: Section) -> dict[str, Any]:
    """A section as the editor (and the import format) expects it: round-trips through save."""
    labels = {p.id: p.label for passage in section.passages for p in passage.paragraphs}
    return {
        "section_no": section.section_no,
        "title": section.title,
        "instructions": section.instructions,
        "context": section.context,
        "audio_asset_id": section.audio_asset_id,
        "duration_seconds": section.duration_seconds,
        "passages": [
            {
                "title": p.title,
                "body": p.body,
                "paragraphs": [
                    {"label": par.label, "text": par.plain_text} for par in p.paragraphs
                ],
            }
            for p in section.passages
        ],
        "groups": [
            {
                "question_type": g.question_type,
                "instructions": g.instructions,
                "config": g.config,
                "image_asset_id": g.image_asset_id,
                "options": [{"label": o.label, "text": o.text} for o in g.options],
                "questions": [
                    {
                        "lineage_id": q.lineage_id,
                        "number_from": q.number_from,
                        "number_to": q.number_to,
                        "stem": q.stem,
                        "config": q.config,
                        "difficulty": q.difficulty,
                        "tags": list(q.tags),
                        "options": [{"label": o.label, "text": o.text} for o in q.options],
                        "answers": _answers(q),
                        "explanation": (
                            {
                                "body": q.explanation.body,
                                "evidence_paragraph_label": labels.get(
                                    q.explanation.evidence_paragraph_id
                                )
                                if q.explanation.evidence_paragraph_id
                                else None,
                                "audio_start_ms": q.explanation.audio_start_ms,
                                "audio_end_ms": q.explanation.audio_end_ms,
                            }
                            if q.explanation
                            else None
                        ),
                    }
                    for q in g.questions
                ],
            }
            for g in section.groups
        ],
    }


@dataclass(frozen=True)
class EditorDocument:
    test: Test
    edition: BookEdition
    book: Book
    version: TestVersion
    module: TestModule
    assets: list[MediaAsset]
    versions: list[TestVersion]


def content_module(version: TestVersion) -> TestModule:
    """The version's single content module (any kind)."""
    if not version.modules:
        raise ContentStateError("This version has no module.")
    return version.modules[0]


async def editor_document(session: AsyncSession, version_id: uuid.UUID) -> EditorDocument:
    version = await service.load_version_tree(session, version_id)
    module = content_module(version)
    test = await session.get_one(Test, version.test_id)
    edition = await session.get_one(BookEdition, test.edition_id)
    book = await session.get_one(Book, edition.book_id)
    asset_ids = service.referenced_asset_ids(version)
    assets = (
        list(await session.scalars(select(MediaAsset).where(MediaAsset.id.in_(asset_ids))))
        if asset_ids
        else []
    )
    versions = list(
        await session.scalars(
            select(TestVersion)
            .where(TestVersion.test_id == test.id)
            .order_by(TestVersion.version_no.desc())
        )
    )
    return EditorDocument(test, edition, book, version, module, assets, versions)


# ------------------------------------------------------------------------------ preview
async def admin_preview(session: AsyncSession, version_id: uuid.UUID) -> dict[str, Any]:
    """What a candidate would see (handler student views), plus answers for the admin only.
    Not an attempt: nothing is scored or stored."""
    version = await service.load_version_tree(session, version_id)
    module = content_module(version)
    test = await session.get_one(Test, version.test_id)
    sections = []
    for section in module.sections:
        groups = []
        for group in section.groups:
            view = get_handler(group.question_type).student_view(group_to_dto(group))
            view["image_asset_id"] = group.image_asset_id
            view["answers"] = [
                {
                    "number_from": q.number_from,
                    "number_to": q.number_to,
                    "accepted": [
                        [k.canonical_value, *[v.value for v in k.variants]] for k in q.answer_keys
                    ],
                    "explanation": q.explanation.body if q.explanation else None,
                }
                for q in group.questions
            ]
            groups.append(view)
        sections.append(
            {
                "section_no": section.section_no,
                "title": section.title,
                "instructions": section.instructions,
                "context": section.context,
                "audio_asset_id": section.audio_asset_id,
                "passages": [
                    {
                        "title": p.title,
                        "paragraphs": [
                            {"label": par.label, "text": par.plain_text} for par in p.paragraphs
                        ],
                    }
                    for p in section.passages
                ],
                "groups": groups,
            }
        )
    return {
        "test_id": test.id,
        "version_id": version.id,
        "version_no": version.version_no,
        "status": version.status,
        "title": test.title,
        "code": test.code,
        "description": version.description,
        "difficulty": version.difficulty,
        "duration_seconds": module.duration_seconds,
        "module": module.module,
        "variant": module.variant,
        "sections": sections,
        "writing_tasks": writing_tasks_document(module),
        "speaking_parts": speaking_parts_document(module),
    }


# ------------------------------------------------------------------------------ workflow
async def submit(
    session: AsyncSession, version_id: uuid.UUID, *, actor_id: uuid.UUID
) -> list[ValidationIssue]:
    return await service.submit_for_review(session, version_id, actor_id=actor_id)


async def review(
    session: AsyncSession,
    version_id: uuid.UUID,
    *,
    reviewer_id: uuid.UUID,
    decision: ReviewDecision,
    comment: str | None,
) -> ContentReview:
    return await service.review_version(
        session, version_id, reviewer_id=reviewer_id, decision=decision, comment=comment
    )


async def publish(
    session: AsyncSession, version_id: uuid.UUID, *, actor_id: uuid.UUID
) -> TestVersion:
    return await service.publish_version(session, version_id, actor_id=actor_id)


async def archive(session: AsyncSession, version_id: uuid.UUID, *, actor_id: uuid.UUID) -> None:
    """Take a published test out of the library (published -> archived, no successor)."""
    await service.unpublish_version(session, version_id, actor_id=actor_id)


def writing_tasks_document(module: TestModule) -> list[dict[str, Any]]:
    from app.modules.content import productive

    return productive.writing_tasks_document(module)


def speaking_parts_document(module: TestModule) -> list[dict[str, Any]]:
    from app.modules.content import productive

    return productive.speaking_parts_document(module)


def listening_question_types(module: str = LISTENING) -> list[tuple[str, str, list[str]]]:
    """(code, handler family, modules) for every registry type usable in the module."""
    return [
        (code, get_handler(code).family, sorted(TYPE_MODULES[code]))
        for code in module_types(module)
    ]
