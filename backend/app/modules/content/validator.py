"""Version validator: the gate for import, review submission and publishing
(docs/CONTENT_MANAGEMENT_ARCHITECTURE.md §7).

Two stages:
- "import": malformed content is an error; incomplete content (e.g. missing audio, which cannot be
  uploaded before Phase 5b) is a warning, so drafts can be imported and completed later.
- "publish": the same completeness checks are errors (used for submit-for-review and publish).

Operates on an in-memory ORM tree (persisted or transient), so import dry-runs validate without
writing content rows.
"""

import uuid
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from app.modules.content.enums import AssetStatus, ModuleKind, ModuleVariant, WritingTaskKind
from app.modules.content.models import ContentLicence, MediaAsset, TestModule, TestVersion
from app.modules.content.question_types import REGISTRY
from app.modules.content.question_types.base import ValidationIssue, error, warning
from app.modules.content.question_types.catalog import TYPE_MODULES
from app.modules.content.richtext import validate_doc
from app.modules.content.tree import group_to_dto

Stage = Literal["import", "publish"]

QUESTIONS_PER_OBJECTIVE_MODULE = 40
_ALLOWED_VARIANTS: dict[str, set[str]] = {
    ModuleKind.LISTENING: {ModuleVariant.COMMON},
    ModuleKind.SPEAKING: {ModuleVariant.COMMON},
    ModuleKind.READING: {ModuleVariant.ACADEMIC, ModuleVariant.GENERAL},
    ModuleKind.WRITING: {ModuleVariant.ACADEMIC, ModuleVariant.GENERAL},
}
_SECTIONS: dict[str, set[int]] = {
    ModuleKind.LISTENING: {1, 2, 3, 4},
    ModuleKind.READING: {1, 2, 3},
}


@dataclass(frozen=True)
class ValidationContext:
    today: date
    stage: Stage
    licence: ContentLicence | None
    assets: Mapping[uuid.UUID, MediaAsset] = field(default_factory=dict)
    # (module, variant) pairs that have a default band-conversion table.
    band_tables: frozenset[tuple[str, str]] = frozenset()


class _Collector:
    def __init__(self, stage: Stage) -> None:
        self.stage = stage
        self.issues: list[ValidationIssue] = []

    def error(self, code: str, location: str, message: str) -> None:
        self.issues.append(error(code, location, message))

    def warning(self, code: str, location: str, message: str) -> None:
        self.issues.append(warning(code, location, message))

    def completeness(self, code: str, location: str, message: str) -> None:
        """Missing-but-addable content: warning at import, error at publish."""
        (self.error if self.stage == "publish" else self.warning)(code, location, message)


def validate_version(version: TestVersion, ctx: ValidationContext) -> list[ValidationIssue]:
    out = _Collector(ctx.stage)
    _check_licence(ctx, out)
    if not version.modules:
        out.error("modules_missing", "version", "A test version needs at least one module.")
    seen = Counter((m.module, m.variant) for m in version.modules)
    for (kind, variant), count in seen.items():
        if count > 1:
            out.error("module_duplicate", f"{kind}/{variant}", "Module/variant appears twice.")
    for module in version.modules:
        location = f"{module.module}/{module.variant}"
        if module.variant not in _ALLOWED_VARIANTS.get(module.module, set()):
            out.error(
                "module_variant_invalid", location, f"{module.module} cannot be {module.variant}."
            )
        if module.module in (ModuleKind.LISTENING, ModuleKind.READING):
            _check_objective_module(module, location, ctx, out)
        elif module.module == ModuleKind.WRITING:
            _check_writing(module, location, ctx, out)
        elif module.module == ModuleKind.SPEAKING:
            _check_speaking(module, location, out)
    return out.issues


def has_errors(issues: list[ValidationIssue]) -> bool:
    return any(issue.is_error for issue in issues)


def _check_licence(ctx: ValidationContext, out: _Collector) -> None:
    if ctx.licence is None:
        out.error("licence_missing", "licence", "Content must reference a licence record.")
    elif not ctx.licence.is_valid_on(ctx.today):
        out.error(
            "licence_invalid",
            "licence",
            f"Licence {ctx.licence.id} is not valid on {ctx.today.isoformat()}.",
        )


def _check_asset(
    asset_id: uuid.UUID | None, location: str, ctx: ValidationContext, out: _Collector
) -> None:
    if asset_id is None:
        return
    asset = ctx.assets.get(asset_id)
    if asset is None:
        out.error("asset_not_found", location, f"Media asset {asset_id} does not exist.")
    elif asset.status != AssetStatus.READY:
        out.completeness("asset_not_ready", location, f"Media asset {asset_id} is {asset.status}.")


def _check_doc(
    doc: object, location: str, out: _Collector, code: str = "rich_text_invalid"
) -> None:
    errors, _ = validate_doc(doc)
    for message in errors:
        out.error(code, location, message)


def _check_objective_module(
    module: TestModule, location: str, ctx: ValidationContext, out: _Collector
) -> None:
    numbers: list[int] = []
    expected_sections = _SECTIONS[module.module]
    present = {s.section_no for s in module.sections}
    if present != expected_sections:
        out.completeness(
            "sections_incomplete",
            location,
            f"Expected sections {sorted(expected_sections)}, found {sorted(present)}.",
        )
    for section in module.sections:
        where = f"{location} > section {section.section_no}"
        if module.module == ModuleKind.LISTENING:
            if section.audio_asset_id is None:
                out.completeness("listening_audio_missing", where, "Listening sections need audio.")
            _check_asset(section.audio_asset_id, where, ctx, out)
        if module.module == ModuleKind.READING and not section.passages:
            out.completeness("passage_missing", where, "Reading sections need a passage.")
        for passage in section.passages:
            _check_doc(passage.body, f"{where} > passage {passage.sort_order}", out)
        if not section.groups:
            out.completeness("questions_missing", where, "Section has no question groups.")
        for index, group in enumerate(section.groups, start=1):
            group_where = f"{where} > group {index} ({group.question_type})"
            handler = REGISTRY.get(group.question_type)
            if handler is None:
                out.error(
                    "question_type_unknown", group_where, f"Unknown type {group.question_type!r}."
                )
                continue
            if module.module not in _modules_for(group.question_type):
                out.error(
                    "question_type_not_in_module",
                    group_where,
                    f"{group.question_type} is not used in {module.module}.",
                )
            _check_asset(group.image_asset_id, group_where, ctx, out)
            out.issues.extend(handler.validate_authoring(group_to_dto(group), group_where))
            for question in group.questions:
                numbers.extend(range(question.number_from, question.number_to + 1))
                q_where = f"{group_where} > Q{question.number_from}"
                if question.stem is not None:
                    _check_doc(question.stem, f"{q_where} > stem", out)
                if question.explanation is None:
                    out.warning("explanation_missing", q_where, "No explanation yet.")
                else:
                    _check_doc(question.explanation.body, f"{q_where} > explanation", out)
    _check_numbering(numbers, location, out)
    if (module.module, module.variant) not in ctx.band_tables:
        out.warning(
            "band_table_missing",
            location,
            "No default band-conversion table for this module/variant; raw scores only.",
        )


def _check_numbering(numbers: list[int], location: str, out: _Collector) -> None:
    duplicates = sorted(n for n, c in Counter(numbers).items() if c > 1)
    if duplicates:
        out.error("question_numbers_duplicate", location, f"Duplicate numbers: {duplicates}.")
    unique = sorted(set(numbers))
    if unique and unique != list(range(1, unique[-1] + 1)):
        out.error(
            "question_numbers_not_contiguous",
            location,
            "Question numbers must run 1..N without gaps.",
        )
    if len(unique) != QUESTIONS_PER_OBJECTIVE_MODULE:
        out.completeness(
            "question_count",
            location,
            f"A full module has {QUESTIONS_PER_OBJECTIVE_MODULE} questions; found {len(unique)}.",
        )


def _check_writing(
    module: TestModule, location: str, ctx: ValidationContext, out: _Collector
) -> None:
    tasks = {t.task_no: t for t in module.writing_tasks}
    if set(tasks) != {1, 2}:
        out.completeness("writing_tasks_incomplete", location, "Writing needs Task 1 and Task 2.")
    expected_task1 = (
        WritingTaskKind.ACADEMIC_REPORT
        if module.variant == ModuleVariant.ACADEMIC
        else WritingTaskKind.GT_LETTER
    )
    for task in module.writing_tasks:
        where = f"{location} > task {task.task_no}"
        expected = expected_task1 if task.task_no == 1 else WritingTaskKind.ESSAY
        if task.task_kind != expected:
            out.error("writing_task_kind", where, f"Task {task.task_no} must be {expected}.")
        _check_doc(task.prompt, f"{where} > prompt", out)
        _check_asset(task.image_asset_id, where, ctx, out)
        if not _has_text(task.prompt):
            out.completeness("writing_prompt_missing", where, "The task has no prompt.")
        if (
            task.task_no == 1
            and module.variant == ModuleVariant.ACADEMIC
            and not task.image_asset_id
        ):
            out.warning(
                "writing_visual_missing",
                where,
                "Academic Task 1 usually has a visual (chart, map, diagram); none is attached.",
            )


def _has_text(doc: object) -> bool:
    def walk(node: object) -> bool:
        if isinstance(node, dict):
            if node.get("type") == "text" and str(node.get("text", "")).strip():
                return True
            return any(walk(c) for c in node.get("content") or [])
        return False

    return walk(doc)


def _check_speaking(module: TestModule, location: str, out: _Collector) -> None:
    parts = {p.part_no: p for p in module.speaking_parts}
    if set(parts) != {1, 2, 3}:
        out.completeness("speaking_parts_incomplete", location, "Speaking needs Parts 1, 2 and 3.")
    for part in module.speaking_parts:
        where = f"{location} > part {part.part_no}"
        if part.part_no == 2 and not part.cue_card:
            out.error("cue_card_missing", where, "Part 2 needs a cue card.")
        if part.part_no in (1, 3) and not part.questions:
            out.completeness("speaking_questions_missing", where, "Part has no questions.")
        if not part.topic.strip():
            out.completeness("speaking_topic_missing", where, "The part has no topic.")


def _modules_for(code: str) -> frozenset[str]:
    return TYPE_MODULES.get(code, frozenset())
