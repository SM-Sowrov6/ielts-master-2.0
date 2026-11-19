"""JSON content import: dry-run then commit (docs/CONTENT_MANAGEMENT_ARCHITECTURE.md §6).

- Dry-run parses and validates the payload into an in-memory tree and records an `import_jobs`
  row with its issues. It never writes content rows.
- Commit rebuilds the tree from the stored payload snapshot, creates or reuses the catalogue
  entries (book/edition/test by natural key) and adds the tree as a new **draft** version.
  Committing a job twice is rejected.

Imports never publish. Real third-party content must not be imported until content rights are
settled (D-04); the licence gate in the validator applies at import time too.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit import api as audit
from app.modules.content.enums import (
    BodyFormat,
    Difficulty,
    EditionVariant,
    ImportStatus,
    IssueSeverity,
    MatchMode,
    ModuleKind,
    ModuleVariant,
    WritingTaskKind,
)
from app.modules.content.errors import (
    CatalogConflictError,
    ContentNotFoundError,
    ContentValidationError,
    ImportJobStateError,
    OpenDraftExistsError,
)
from app.modules.content.models import (
    AnswerKey,
    AnswerVariant,
    Book,
    BookEdition,
    ContentLicence,
    Explanation,
    ImportJob,
    ImportJobIssue,
    Paragraph,
    Passage,
    Question,
    QuestionGroup,
    QuestionOption,
    Section,
    SpeakingPart,
    SpeakingQuestion,
    Test,
    TestModule,
    TestVersion,
    WritingTask,
)
from app.modules.content.question_types import REGISTRY
from app.modules.content.question_types.base import ValidationIssue, error
from app.modules.content.question_types.normalize import KeyNotationError, expand_key_notation
from app.modules.content.service import (
    build_validation_context,
    next_version_no,
    open_version_exists,
)
from app.modules.content.validator import has_errors, validate_version
from app.shared.ids import new_id

_STRICT = ConfigDict(extra="forbid")
RichText = dict[str, Any]


# ------------------------------------------------------------------------- payload schema
class OptionIn(BaseModel):
    model_config = _STRICT
    label: str = Field(min_length=1, max_length=20)
    text: str = Field(min_length=1, max_length=2000)


class AnswerIn(BaseModel):
    model_config = _STRICT
    value: str = Field(
        min_length=1, max_length=500, description="Key notation, e.g. '(the) library'"
    )
    slot: int | None = Field(default=None, ge=1)
    match_mode: MatchMode | None = None


class ExplanationIn(BaseModel):
    model_config = _STRICT
    body: RichText
    evidence_paragraph_label: str | None = None
    audio_start_ms: int | None = Field(default=None, ge=0)
    audio_end_ms: int | None = Field(default=None, ge=0)


class QuestionIn(BaseModel):
    model_config = _STRICT
    # Stable identity across versions/edits (optional; a new lineage is assigned when absent).
    lineage_id: uuid.UUID | None = None
    number_from: int = Field(ge=1, le=40)
    number_to: int | None = Field(default=None, ge=1, le=40)
    stem: RichText | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    difficulty: Difficulty | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)
    options: list[OptionIn] = Field(default_factory=list)
    answers: list[AnswerIn] = Field(min_length=1)
    explanation: ExplanationIn | None = None


class GroupIn(BaseModel):
    model_config = _STRICT
    question_type: str
    instructions: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    image_asset_id: uuid.UUID | None = None
    options: list[OptionIn] = Field(default_factory=list)
    questions: list[QuestionIn] = Field(min_length=1)


class ParagraphIn(BaseModel):
    model_config = _STRICT
    label: str | None = Field(default=None, max_length=10)
    text: str = Field(min_length=1)


class PassageIn(BaseModel):
    model_config = _STRICT
    title: str | None = None
    body: RichText
    paragraphs: list[ParagraphIn] = Field(default_factory=list)


class SectionIn(BaseModel):
    model_config = _STRICT
    section_no: int = Field(ge=1, le=4)
    title: str | None = Field(default=None, max_length=300)
    instructions: str | None = Field(default=None, max_length=5000)
    context: str | None = Field(default=None, max_length=2000)
    audio_asset_id: uuid.UUID | None = None
    duration_seconds: int | None = Field(default=None, gt=0)
    passages: list[PassageIn] = Field(default_factory=list)
    groups: list[GroupIn] = Field(default_factory=list)


class WritingTaskIn(BaseModel):
    model_config = _STRICT
    task_no: Literal[1, 2]
    task_kind: WritingTaskKind
    prompt: RichText
    image_asset_id: uuid.UUID | None = None
    min_words: int = Field(gt=0)
    key_features: list[str] = Field(default_factory=list)


class SpeakingQuestionIn(BaseModel):
    model_config = _STRICT
    text: str = Field(min_length=1)
    is_follow_up: bool = False


class SpeakingPartIn(BaseModel):
    model_config = _STRICT
    part_no: Literal[1, 2, 3]
    topic: str = Field(min_length=1, max_length=300)
    cue_card: dict[str, Any] | None = None
    questions: list[SpeakingQuestionIn] = Field(default_factory=list)


class ModuleIn(BaseModel):
    model_config = _STRICT
    module: ModuleKind
    variant: ModuleVariant
    duration_seconds: int | None = Field(default=None, gt=0)
    sections: list[SectionIn] = Field(default_factory=list)
    writing_tasks: list[WritingTaskIn] = Field(default_factory=list)
    speaking_parts: list[SpeakingPartIn] = Field(default_factory=list)


class BookIn(BaseModel):
    model_config = _STRICT
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)
    title: str = Field(min_length=1, max_length=300)
    series: str | None = None
    category: str | None = None
    description: str | None = None
    is_premium: bool = False


class EditionIn(BaseModel):
    model_config = _STRICT
    label: str = Field(min_length=1, max_length=100)
    publication_year: int | None = Field(default=None, ge=1980, le=2100)
    variant: EditionVariant


class TestIn(BaseModel):
    model_config = _STRICT
    __test__ = False  # not a pytest test class
    code: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=300)
    sort_order: int = 0


class CatalogIn(BaseModel):
    model_config = _STRICT
    book: BookIn
    edition: EditionIn
    test: TestIn


class TestVersionImport(BaseModel):
    """Canonical import format (JSON Schema: docs/schemas/test-version-import.schema.json)."""

    model_config = _STRICT
    __test__ = False
    schema_version: Literal[1] = 1
    catalog: CatalogIn
    change_note: str | None = None
    description: str | None = Field(default=None, max_length=5000)
    difficulty: Difficulty | None = None
    tags: list[Annotated[str, Field(min_length=1, max_length=50)]] = Field(
        default_factory=list, max_length=20
    )
    modules: list[ModuleIn] = Field(min_length=1)


def import_json_schema() -> dict[str, Any]:
    return TestVersionImport.model_json_schema()


# ------------------------------------------------------------------------------------ build tree
def _default_match_mode(question_type: str, config: dict[str, Any]) -> MatchMode:
    handler = REGISTRY.get(question_type)
    family = handler.family if handler else "text"
    if family == "multi_option":
        return MatchMode.SET_MEMBER
    if family == "option" or config.get("answer_format") == "option":
        return MatchMode.OPTION
    return MatchMode.TEXT


def _build_module(m_index: int, module_in: ModuleIn, issues: list[ValidationIssue]) -> TestModule:
    """One module tree (transient ORM objects); appends key-notation issues to `issues`."""
    m_loc = f"{module_in.module.value}/{module_in.variant.value}"
    sections: list[Section] = []
    for section_in in module_in.sections:
        s_loc = f"{m_loc} > section {section_in.section_no}"
        paragraph_by_label: dict[str, Paragraph] = {}
        passages: list[Passage] = []
        for p_index, passage_in in enumerate(section_in.passages):
            paragraphs = []
            for par_index, par in enumerate(passage_in.paragraphs):
                paragraph = Paragraph(
                    id=new_id(), label=par.label, sort_order=par_index, plain_text=par.text
                )
                if par.label:
                    paragraph_by_label[par.label] = paragraph
                paragraphs.append(paragraph)
            passages.append(
                Passage(
                    sort_order=p_index,
                    title=passage_in.title,
                    body_format=BodyFormat.PROSEMIRROR_JSON.value,
                    body=passage_in.body,
                    word_count=sum(len(p.text.split()) for p in passage_in.paragraphs) or None,
                    paragraphs=paragraphs,
                )
            )
        groups: list[QuestionGroup] = []
        for g_index, group_in in enumerate(section_in.groups):
            g_loc = f"{s_loc} > group {g_index + 1} ({group_in.question_type})"
            default_mode = _default_match_mode(group_in.question_type, group_in.config)
            questions: list[Question] = []
            for q_in in group_in.questions:
                number_to = q_in.number_to or q_in.number_from
                q_loc = f"{g_loc} > Q{q_in.number_from}"
                keys: list[AnswerKey] = []
                for a_index, answer in enumerate(q_in.answers, start=1):
                    mode = answer.match_mode or default_mode
                    if mode in (MatchMode.TEXT,):
                        try:
                            accepted = expand_key_notation(answer.value)
                        except KeyNotationError as exc:
                            issues.append(error("key_notation_invalid", q_loc, str(exc)))
                            continue
                    else:
                        accepted = [answer.value.strip()]
                    keys.append(
                        AnswerKey(
                            slot=answer.slot or a_index,
                            canonical_value=accepted[0],
                            notation=answer.value,
                            match_mode=mode.value,
                            variants=[AnswerVariant(value=v) for v in accepted[1:]],
                        )
                    )
                explanation = None
                if q_in.explanation is not None:
                    evidence = None
                    label = q_in.explanation.evidence_paragraph_label
                    if label is not None:
                        evidence = paragraph_by_label.get(label)
                        if evidence is None:
                            issues.append(
                                error(
                                    "evidence_paragraph_unknown",
                                    q_loc,
                                    f"No paragraph {label!r}.",
                                )
                            )
                    explanation = Explanation(
                        body=q_in.explanation.body,
                        evidence_paragraph_id=evidence.id if evidence else None,
                        audio_start_ms=q_in.explanation.audio_start_ms,
                        audio_end_ms=q_in.explanation.audio_end_ms,
                    )
                if number_to < q_in.number_from:
                    issues.append(error("number_range", q_loc, "number_to is below number_from."))
                    number_to = q_in.number_from
                questions.append(
                    Question(
                        lineage_id=q_in.lineage_id or new_id(),
                        number_from=q_in.number_from,
                        number_to=number_to,
                        marks=number_to - q_in.number_from + 1,
                        stem=q_in.stem,
                        config=q_in.config,
                        difficulty=q_in.difficulty.value if q_in.difficulty else None,
                        tags=q_in.tags,
                        options=[
                            QuestionOption(label=o.label, text=o.text, sort_order=i)
                            for i, o in enumerate(q_in.options)
                        ],
                        answer_keys=keys,
                        explanation=explanation,
                    )
                )
            groups.append(
                QuestionGroup(
                    question_type=group_in.question_type,
                    instructions=group_in.instructions,
                    config=group_in.config,
                    image_asset_id=group_in.image_asset_id,
                    sort_order=g_index,
                    options=[
                        QuestionOption(label=o.label, text=o.text, sort_order=i)
                        for i, o in enumerate(group_in.options)
                    ],
                    questions=questions,
                )
            )
        sections.append(
            Section(
                section_no=section_in.section_no,
                title=section_in.title,
                instructions=section_in.instructions,
                context=section_in.context,
                audio_asset_id=section_in.audio_asset_id,
                duration_seconds=section_in.duration_seconds,
                passages=passages,
                groups=groups,
            )
        )
    return TestModule(
        module=module_in.module.value,
        variant=module_in.variant.value,
        duration_seconds=module_in.duration_seconds,
        sort_order=m_index,
        sections=sections,
        writing_tasks=[
            WritingTask(
                task_no=t.task_no,
                task_kind=t.task_kind.value,
                prompt=t.prompt,
                image_asset_id=t.image_asset_id,
                min_words=t.min_words,
                key_features=t.key_features,
            )
            for t in module_in.writing_tasks
        ],
        speaking_parts=[
            SpeakingPart(
                part_no=p.part_no,
                topic=p.topic,
                cue_card=p.cue_card,
                questions=[
                    SpeakingQuestion(text=q.text, sort_order=i, is_follow_up=q.is_follow_up)
                    for i, q in enumerate(p.questions)
                ],
            )
            for p in module_in.speaking_parts
        ],
    )


def build_version_tree(payload: TestVersionImport) -> tuple[TestVersion, list[ValidationIssue]]:
    """Transient ORM tree (not added to any session) plus key-notation issues."""
    issues: list[ValidationIssue] = []
    modules = [
        _build_module(m_index, module_in, issues)
        for m_index, module_in in enumerate(payload.modules)
    ]
    version = TestVersion(
        change_note=payload.change_note,
        description=payload.description,
        difficulty=payload.difficulty.value if payload.difficulty else None,
        tags=list(payload.tags),
        modules=modules,
        reviews=[],
    )
    return version, issues


def build_sections(
    sections: list[SectionIn], module: str = "listening", variant: str = "common"
) -> tuple[list[Section], list[ValidationIssue]]:
    """Section trees for one module (the admin editor rebuilds a draft module with this)."""
    issues: list[ValidationIssue] = []
    module_in = ModuleIn(
        module=ModuleKind(module), variant=ModuleVariant(variant), sections=sections
    )
    return _build_module(0, module_in, issues).sections, issues


# ------------------------------------------------------------------------- dry-run / commit
@dataclass(frozen=True)
class DryRunResult:
    job: ImportJob
    issues: list[ValidationIssue]

    @property
    def ok(self) -> bool:
        return not has_errors(self.issues)


def _schema_issues(exc: ValidationError) -> list[ValidationIssue]:
    return [
        error("schema_invalid", ".".join(str(p) for p in e["loc"]) or "payload", e["msg"])
        for e in exc.errors()
    ]


async def _existing_test(session: AsyncSession, catalog: CatalogIn) -> Test | None:
    return await session.scalar(
        select(Test)
        .join(BookEdition, BookEdition.id == Test.edition_id)
        .join(Book, Book.id == BookEdition.book_id)
        .where(
            Book.slug == catalog.book.slug,
            BookEdition.edition_label == catalog.edition.label,
            Test.code == catalog.test.code,
        )
    )


async def dry_run(
    session: AsyncSession,
    raw: bytes,
    *,
    file_name: str,
    license_id: uuid.UUID,
    actor_id: uuid.UUID | None,
) -> DryRunResult:
    """Validate an import file and record the job. Writes no content rows."""
    licence = await session.get(ContentLicence, license_id)
    if licence is None:
        raise ContentNotFoundError(f"Licence {license_id} not found.")
    issues: list[ValidationIssue] = []
    payload_dict: dict[str, Any] = {}
    try:
        payload_dict = json.loads(raw)
        payload = TestVersionImport.model_validate(payload_dict)
    except json.JSONDecodeError as exc:
        issues.append(error("json_invalid", "payload", str(exc)))
        payload = None
    except ValidationError as exc:
        issues.extend(_schema_issues(exc))
        payload = None

    if payload is not None:
        version, build_issues = build_version_tree(payload)
        issues.extend(build_issues)
        context = await build_validation_context(session, version, stage="import", licence=licence)
        issues.extend(validate_version(version, context))
        existing = await _existing_test(session, payload.catalog)
        if existing is not None and await open_version_exists(session, existing.id):
            issues.append(
                error("open_draft_exists", "catalog.test", "This test already has an open draft.")
            )
        book = await session.scalar(select(Book).where(Book.slug == payload.catalog.book.slug))
        if book is not None and book.license_id != license_id:
            issues.append(
                error("licence_mismatch", "catalog.book", "Book exists under a different licence.")
            )

    job = ImportJob(
        status=(ImportStatus.FAILED if has_errors(issues) else ImportStatus.VALIDATED).value,
        file_name=file_name,
        file_sha256=hashlib.sha256(raw).hexdigest(),
        uploaded_by=actor_id,
        license_id=license_id,
        payload=payload_dict if isinstance(payload_dict, dict) else {},
        summary={
            "errors": sum(1 for i in issues if i.is_error),
            "warnings": sum(1 for i in issues if not i.is_error),
        },
        issues=[
            ImportJobIssue(
                severity=i.severity.value, code=i.code, location=i.location, message=i.message
            )
            for i in issues
        ],
    )
    session.add(job)
    await session.flush()
    await audit.record(
        session,
        actor_id=actor_id,
        action="content.import.dry_run",
        entity_type="import_job",
        entity_id=job.id,
        changes={"file_sha256": job.file_sha256, **job.summary},
    )
    return DryRunResult(job=job, issues=issues)


async def commit(session: AsyncSession, job_id: uuid.UUID, *, actor_id: uuid.UUID) -> TestVersion:
    """Create the draft version from a validated job (idempotency: a job commits at most once)."""
    job = await session.scalar(select(ImportJob).where(ImportJob.id == job_id).with_for_update())
    if job is None:
        raise ContentNotFoundError(f"Import job {job_id} not found.")
    if job.status != ImportStatus.VALIDATED:
        raise ImportJobStateError(f"Job is {job.status}; only validated jobs can be committed.")
    payload = TestVersionImport.model_validate(job.payload)
    version, build_issues = build_version_tree(payload)
    licence = await session.get_one(ContentLicence, job.license_id)
    context = await build_validation_context(session, version, stage="import", licence=licence)
    issues = build_issues + validate_version(version, context)
    if has_errors(issues):  # e.g. licence expired since the dry-run
        raise ContentValidationError(issues)

    test = await _upsert_catalog(session, payload.catalog, license_id=job.license_id)
    if await open_version_exists(session, test.id):
        raise OpenDraftExistsError()
    version.test_id = test.id
    version.version_no = await next_version_no(session, test.id)
    version.created_by = actor_id
    session.add(version)
    await session.flush()

    job.status = ImportStatus.COMMITTED.value
    job.committed_at = datetime.now(UTC)
    job.result_test_version_id = version.id
    await audit.record(
        session,
        actor_id=actor_id,
        action="content.import.commit",
        entity_type="import_job",
        entity_id=job.id,
        changes={"test_version_id": str(version.id), "test_id": str(test.id)},
    )
    await session.flush()
    return version


async def _upsert_catalog(
    session: AsyncSession, catalog: CatalogIn, *, license_id: uuid.UUID
) -> Test:
    book = await session.scalar(
        select(Book).where(Book.slug == catalog.book.slug).with_for_update()
    )
    if book is None:
        book = Book(
            slug=catalog.book.slug,
            title=catalog.book.title,
            series=catalog.book.series,
            category=catalog.book.category,
            description=catalog.book.description,
            is_premium=catalog.book.is_premium,
            license_id=license_id,
        )
        session.add(book)
        await session.flush()
    elif book.license_id != license_id:
        raise CatalogConflictError("Book exists under a different licence.")
    edition = await session.scalar(
        select(BookEdition).where(
            BookEdition.book_id == book.id, BookEdition.edition_label == catalog.edition.label
        )
    )
    if edition is None:
        edition = BookEdition(
            book_id=book.id,
            edition_label=catalog.edition.label,
            publication_year=catalog.edition.publication_year,
            variant=catalog.edition.variant.value,
        )
        session.add(edition)
        await session.flush()
    test = await session.scalar(
        select(Test).where(Test.edition_id == edition.id, Test.code == catalog.test.code)
    )
    if test is None:
        test = Test(
            edition_id=edition.id,
            code=catalog.test.code,
            title=catalog.test.title,
            sort_order=catalog.test.sort_order,
        )
        session.add(test)
        await session.flush()
    return test


def issue_severity_counts(issues: list[ValidationIssue]) -> dict[str, int]:
    return {
        "errors": sum(1 for i in issues if i.severity is IssueSeverity.ERROR),
        "warnings": sum(1 for i in issues if i.severity is IssueSeverity.WARNING),
    }
