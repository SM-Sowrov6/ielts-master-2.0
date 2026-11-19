"""Admin authoring of Writing and Speaking tests on the existing content domain.

Same aggregate and workflow as the objective modules (`authoring`): a catalogue `Test` whose
versions hold one `writing/<academic|general>` module (Task 1 + Task 2) or one
`speaking/common` module (Parts 1-3). Drafts replace the module's tasks/parts; submit, four-eyes
review, publish, archive and new revisions reuse `service` unchanged. Model answers are
`sample_answers` rows carrying the test's licence; they join the immutability guard and are
shown to candidates only after they submit.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit import api as audit
from app.modules.content import service
from app.modules.content.authoring import (
    CreateListeningTestIn,
    SaveResult,
    _code_taken,
)
from app.modules.content.enums import (
    AssetKind,
    ModuleKind,
    ModuleVariant,
    VersionStatus,
    WritingTaskKind,
)
from app.modules.content.errors import (
    CatalogConflictError,
    ContentNotFoundError,
    ContentStateError,
    ContentValidationError,
    DraftConflictError,
)
from app.modules.content.models import (
    BookEdition,
    MediaAsset,
    SampleAnswer,
    SpeakingPart,
    SpeakingQuestion,
    Test,
    TestModule,
    TestVersion,
    WritingTask,
)
from app.modules.content.question_types.base import ValidationIssue, error
from app.modules.content.richtext import plain_doc
from app.modules.content.validator import has_errors

WRITING = ModuleKind.WRITING.value
SPEAKING = ModuleKind.SPEAKING.value
ProductiveModule = Literal["writing", "speaking"]
PRODUCTIVE = (WRITING, SPEAKING)
DEFAULT_MIN_WORDS = {1: 150, 2: 250}
_STRICT = ConfigDict(extra="forbid")
Line = Field(min_length=1, max_length=300)


def _node_text(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return str(node.get("text", ""))
    if node.get("type") == "hardBreak":
        return "\n"
    return "".join(_node_text(child) for child in node.get("content") or [])


def doc_text(doc: Any) -> str:
    """Plain text of a stored document (paragraphs separated by blank lines)."""
    if not isinstance(doc, dict):
        return ""
    blocks = [_node_text(block) for block in doc.get("content") or []]
    return "\n\n".join(b for b in blocks if b.strip())


# ------------------------------------------------------------------------------ inputs
class ModelAnswerIn(BaseModel):
    model_config = _STRICT
    band: float | None = Field(default=None, ge=0, le=9)
    body: str = Field(min_length=1, max_length=10_000)
    author_note: str | None = Field(default=None, max_length=2000)

    @field_validator("band")
    @classmethod
    def _half(cls, value: float | None) -> float | None:
        if value is not None and value * 2 != int(value * 2):
            raise ValueError("Bands are whole or half steps.")
        return value


class WritingTaskIn(BaseModel):
    model_config = _STRICT
    task_no: Literal[1, 2]
    prompt_text: str = Field(default="", max_length=5000)
    image_asset_id: uuid.UUID | None = None
    min_words: int = Field(ge=50, le=400)
    key_features: list[str] = Field(default_factory=list, max_length=10)  # assessment focus
    model_answers: list[ModelAnswerIn] = Field(default_factory=list, max_length=3)


class CueCardIn(BaseModel):
    model_config = _STRICT
    prompt: str = Field(min_length=1, max_length=500)
    points: list[str] = Field(default_factory=list, max_length=6)
    closing: str | None = Field(default=None, max_length=300)


class SpeakingQuestionIn(BaseModel):
    model_config = _STRICT
    text: str = Field(min_length=1, max_length=500)
    is_follow_up: bool = False


class SpeakingPartIn(BaseModel):
    model_config = _STRICT
    part_no: Literal[1, 2, 3]
    topic: str = Field(default="", max_length=300)
    cue_card: CueCardIn | None = None
    questions: list[SpeakingQuestionIn] = Field(default_factory=list, max_length=20)
    model_answers: list[ModelAnswerIn] = Field(default_factory=list, max_length=3)


class SaveProductiveDraftIn(BaseModel):
    model_config = _STRICT
    revision: datetime  # the draft's `updated_at` the editor loaded (optimistic concurrency)
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    difficulty: Literal["easy", "medium", "hard"] | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)
    duration_seconds: int | None = Field(default=None, ge=60, le=4 * 3600)
    admin_notes: str | None = Field(default=None, max_length=5000)
    change_note: str | None = Field(default=None, max_length=2000)
    writing_tasks: list[WritingTaskIn] = Field(default_factory=list, max_length=2)
    speaking_parts: list[SpeakingPartIn] = Field(default_factory=list, max_length=3)


# ------------------------------------------------------------------------------ create
def _task1_kind(variant: str) -> str:
    return (
        WritingTaskKind.ACADEMIC_REPORT.value
        if variant == ModuleVariant.ACADEMIC.value
        else WritingTaskKind.GT_LETTER.value
    )


async def create_productive_test(
    session: AsyncSession,
    data: CreateListeningTestIn,
    *,
    actor_id: uuid.UUID,
    module: str,
    variant: str | None,
) -> TestVersion:
    """A new catalogue test with draft v1: Writing (Task 1 + Task 2, empty prompts) or Speaking
    (Parts 1-3, empty)."""
    if module == WRITING:
        variant = variant or ModuleVariant.ACADEMIC.value
        if variant not in (ModuleVariant.ACADEMIC.value, ModuleVariant.GENERAL.value):
            raise ContentStateError("Writing tests are Academic or General Training.")
    else:
        variant = ModuleVariant.COMMON.value
    if await session.get(BookEdition, data.edition_id) is None:
        raise ContentNotFoundError(f"Edition {data.edition_id} not found.")
    if await _code_taken(session, data.edition_id, data.code):
        raise CatalogConflictError("This edition already has a test with that identifier.")
    test = Test(
        edition_id=data.edition_id, code=data.code, title=data.title, admin_notes=data.admin_notes
    )
    session.add(test)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise CatalogConflictError("This edition already has a test with that identifier.") from exc
    content = TestModule(
        module=module,
        variant=variant,
        duration_seconds=data.duration_seconds,
        sort_order=0,
    )
    if module == WRITING:
        content.writing_tasks = [
            WritingTask(
                task_no=n,
                task_kind=_task1_kind(variant) if n == 1 else WritingTaskKind.ESSAY.value,
                prompt=plain_doc(""),
                min_words=DEFAULT_MIN_WORDS[n],
                key_features=[],
            )
            for n in (1, 2)
        ]
    else:
        content.speaking_parts = [SpeakingPart(part_no=n, topic="") for n in (1, 2, 3)]
    version = TestVersion(
        test_id=test.id,
        version_no=1,
        created_by=actor_id,
        description=data.description,
        difficulty=data.difficulty.value if data.difficulty else None,
        tags=list(data.tags),
        modules=[content],
    )
    session.add(version)
    await session.flush()
    await audit.record(
        session,
        actor_id=actor_id,
        action="content.test.create",
        entity_type="test",
        entity_id=test.id,
        changes={"test_version_id": str(version.id), "module": module, "variant": variant},
    )
    return version


# ------------------------------------------------------------------------------ save
def productive_module(version: TestVersion) -> TestModule:
    for module in version.modules:
        if module.module in PRODUCTIVE:
            return module
    raise ContentStateError("This version has no Writing or Speaking module.")


def _samples(answers: list[ModelAnswerIn], licence_id: uuid.UUID) -> list[SampleAnswer]:
    return [
        SampleAnswer(
            band=Decimal(str(a.band)) if a.band is not None else None,
            body=a.body.strip(),
            license_id=licence_id,
            author_note=a.author_note,
        )
        for a in answers
    ]


async def _image_issues(
    session: AsyncSession, tasks: list[WritingTaskIn], licence_id: uuid.UUID | None, where: str
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for t in tasks:
        if t.image_asset_id is None:
            continue
        location = f"{where} > task {t.task_no}"
        if t.task_no == 2:
            issues.append(error("image_not_allowed", location, "Task 2 has no visual."))
            continue
        asset = await session.get(MediaAsset, t.image_asset_id)
        if asset is None:
            continue  # reported by the validator as asset_not_found
        if asset.kind != AssetKind.IMAGE.value:
            issues.append(error("asset_kind_mismatch", location, "Expected an image file."))
        elif licence_id is not None and asset.license_id != licence_id:
            issues.append(
                error("asset_licence_mismatch", location, "The file belongs to another licence.")
            )
    return issues


async def save_productive_draft(
    session: AsyncSession,
    version_id: uuid.UUID,
    data: SaveProductiveDraftIn,
    *,
    actor_id: uuid.UUID,
) -> SaveResult:
    version = await service.load_version_tree(session, version_id)
    if version.status != VersionStatus.DRAFT:
        raise ContentStateError("Only drafts can be edited. Create a new revision instead.")
    if version.updated_at != data.revision:
        raise DraftConflictError()
    test = await session.get_one(Test, version.test_id, with_for_update=True)
    module = productive_module(version)
    where = f"{module.module}/{module.variant}"
    licence = await service.licence_for_test(session, version.test_id)
    if licence is None:
        raise ContentStateError("The test's book has no licence.")
    issues: list[ValidationIssue] = []
    if module.module == WRITING:
        if data.speaking_parts:
            issues.append(error("parts_not_allowed", where, "Writing tests have no parts."))
        numbers: list[int] = [t.task_no for t in data.writing_tasks]
        if len(numbers) != len(set(numbers)):
            issues.append(error("task_duplicate", where, "Each task number once."))
        issues += await _image_issues(session, data.writing_tasks, licence.id, where)
    else:
        if data.writing_tasks:
            issues.append(error("tasks_not_allowed", where, "Speaking tests have no tasks."))
        numbers = [p.part_no for p in data.speaking_parts]
        if len(numbers) != len(set(numbers)):
            issues.append(error("part_duplicate", where, "Each part number once."))
        for p in data.speaking_parts:
            if p.part_no != 2 and p.cue_card is not None:
                issues.append(
                    error("cue_card_not_allowed", f"{where} > part {p.part_no}", "Only Part 2.")
                )
    if data.title != test.title and test.current_published_version_id is not None:
        issues.append(error("title_locked", "test", "The title of a published test cannot change."))
    if has_errors(issues):
        raise ContentValidationError(issues)

    if module.module == WRITING:
        for task in list(module.writing_tasks):
            module.writing_tasks.remove(task)
        await session.flush()
        module.writing_tasks.extend(
            WritingTask(
                task_no=t.task_no,
                task_kind=_task1_kind(module.variant) if t.task_no == 1 else "essay",
                prompt=plain_doc(t.prompt_text),
                image_asset_id=t.image_asset_id if t.task_no == 1 else None,
                min_words=t.min_words,
                key_features=[k.strip() for k in t.key_features if k.strip()],
                sample_answers=_samples(t.model_answers, licence.id),
            )
            for t in sorted(data.writing_tasks, key=lambda t: t.task_no)
        )
    else:
        for part in list(module.speaking_parts):
            module.speaking_parts.remove(part)
        await session.flush()
        module.speaking_parts.extend(
            SpeakingPart(
                part_no=p.part_no,
                topic=p.topic.strip(),
                cue_card=p.cue_card.model_dump() if p.cue_card else None,
                questions=[
                    SpeakingQuestion(text=q.text.strip(), sort_order=i, is_follow_up=q.is_follow_up)
                    for i, q in enumerate(p.questions)
                ],
                sample_answers=_samples(p.model_answers, licence.id),
            )
            for p in sorted(data.speaking_parts, key=lambda p: p.part_no)
        )
    module.duration_seconds = data.duration_seconds
    version.description = data.description
    version.difficulty = data.difficulty
    version.tags = list(data.tags)
    version.change_note = data.change_note
    version.updated_at = func.now()
    test.title = data.title
    test.admin_notes = data.admin_notes
    await session.flush()
    import_issues = await service.validate_persisted_version(session, version, "import")
    if has_errors(import_issues):
        raise ContentValidationError(import_issues)
    await session.refresh(version, ["updated_at"])
    await audit.record(
        session,
        actor_id=actor_id,
        action="content.test_version.save_draft",
        entity_type="test_version",
        entity_id=version.id,
        changes={"module": module.module},
    )
    reloaded = await service.load_version_tree(session, version.id)
    return SaveResult(
        reloaded, await service.validate_persisted_version(session, reloaded, "publish")
    )


# ------------------------------------------------------------------------------ documents
def _samples_out(samples: list[SampleAnswer]) -> list[dict[str, Any]]:
    return [{"band": a.band, "body": a.body, "author_note": a.author_note} for a in samples]


def writing_tasks_document(module: TestModule) -> list[dict[str, Any]]:
    return [
        {
            "task_no": t.task_no,
            "task_kind": t.task_kind,
            "prompt_text": doc_text(t.prompt),
            "image_asset_id": t.image_asset_id,
            "min_words": t.min_words,
            "key_features": list(t.key_features),
            "model_answers": _samples_out(t.sample_answers),
        }
        for t in sorted(module.writing_tasks, key=lambda t: t.task_no)
    ]


def speaking_parts_document(module: TestModule) -> list[dict[str, Any]]:
    return [
        {
            "part_no": p.part_no,
            "topic": p.topic,
            "cue_card": p.cue_card,
            "questions": [{"text": q.text, "is_follow_up": q.is_follow_up} for q in p.questions],
            "model_answers": _samples_out(p.sample_answers),
        }
        for p in sorted(module.speaking_parts, key=lambda p: p.part_no)
    ]


# ------------------------------------------------------------------------------ delivery
@dataclass(frozen=True)
class TaskRef:
    """What a writing submission snapshots: the immutable task as the candidate saw it."""

    task_id: uuid.UUID
    task_no: int
    snapshot: dict[str, Any]


async def _readable_module(session: AsyncSession, version_id: uuid.UUID, module: str) -> TestModule:
    version = await service.load_version_tree(session, version_id)
    if version.status not in (VersionStatus.PUBLISHED.value, VersionStatus.ARCHIVED.value):
        raise ContentNotFoundError("This test is not available.")
    found = productive_module(version)
    if found.module != module:
        raise ContentNotFoundError("This test is not available.")
    return found


def _task_view(t: WritingTask) -> dict[str, Any]:
    return {
        "task_no": t.task_no,
        "task_kind": t.task_kind,
        "prompt_text": doc_text(t.prompt),
        "min_words": t.min_words,
        "has_image": t.image_asset_id is not None,
        "suggested_minutes": 20 if t.task_no == 1 else 40,
    }


async def writing_student_view(session: AsyncSession, version_id: uuid.UUID) -> dict[str, Any]:
    module = await _readable_module(session, version_id, WRITING)
    return {
        "variant": module.variant,
        "duration_seconds": module.duration_seconds,
        "tasks": [_task_view(t) for t in sorted(module.writing_tasks, key=lambda t: t.task_no)],
    }


async def speaking_student_view(session: AsyncSession, version_id: uuid.UUID) -> dict[str, Any]:
    """Self-practice: the candidate sees the examiner's questions (there is no live examiner)."""
    module = await _readable_module(session, version_id, SPEAKING)
    return {
        "parts": [
            {
                "part_no": p.part_no,
                "topic": p.topic,
                "cue_card": p.cue_card,
                "questions": [q.text for q in p.questions],
                "prep_seconds": 60 if p.part_no == 2 else 0,
                "answer_seconds": 120 if p.part_no == 2 else 60,
            }
            for p in sorted(module.speaking_parts, key=lambda p: p.part_no)
        ]
    }


async def writing_task(session: AsyncSession, version_id: uuid.UUID, task_no: int) -> TaskRef:
    module = await _readable_module(session, version_id, WRITING)
    for t in module.writing_tasks:
        if t.task_no == task_no:
            view = _task_view(t)
            view["key_features"] = list(t.key_features)
            return TaskRef(t.id, t.task_no, view)
    raise ContentNotFoundError("This task is not available.")


async def writing_task_image(
    session: AsyncSession, version_id: uuid.UUID, task_no: int
) -> tuple[str, str]:
    module = await _readable_module(session, version_id, WRITING)
    task = next((t for t in module.writing_tasks if t.task_no == task_no), None)
    asset = (
        await session.get(MediaAsset, task.image_asset_id) if task and task.image_asset_id else None
    )
    if asset is None or asset.status != "ready":
        raise ContentNotFoundError("No image is available for this task.")
    return asset.storage_key, asset.mime_type


async def model_answers(
    session: AsyncSession, version_id: uuid.UUID, module: str, number: int
) -> list[dict[str, Any]]:
    """Model answers of a task (writing) or part (speaking): only call after submission."""
    found = await _readable_module(session, version_id, module)
    items = found.writing_tasks if module == WRITING else found.speaking_parts
    for item in items:
        if (item.task_no if isinstance(item, WritingTask) else item.part_no) == number:
            return _samples_out(item.sample_answers)
    return []
