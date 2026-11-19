"""Versioned assessment rubrics for Writing and Speaking (admin-authored, four-eyes reviewed).

The criteria codes are fixed per module (the four IELTS criteria); their names, descriptions and
band descriptors are written by the platform's own staff. No copyrighted IELTS band descriptors
are shipped or seeded. A new draft starts as a copy of the latest version (or an empty skeleton).
Workflow: draft -> in_review -> (approved by another reviewer) -> published; publishing archives
the previous published version. AI evaluations record the rubric version they used.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.audit import api as audit
from app.modules.content.enums import ReviewDecision
from app.modules.content.errors import (
    CatalogConflictError,
    ContentNotFoundError,
    ContentStateError,
    ContentValidationError,
    DraftConflictError,
    ReviewRequiredError,
    SelfReviewError,
)
from app.modules.content.models import RubricReview, RubricVersion
from app.modules.content.question_types.base import ValidationIssue, error
from app.modules.content.validator import has_errors

RubricModule = Literal["writing", "speaking"]
CRITERIA: dict[str, tuple[tuple[str, str], ...]] = {
    "writing": (
        ("TA", "Task achievement / task response"),
        ("CC", "Coherence and cohesion"),
        ("LR", "Lexical resource"),
        ("GRA", "Grammatical range and accuracy"),
    ),
    "speaking": (
        ("FC", "Fluency and coherence"),
        ("LR", "Lexical resource"),
        ("GRA", "Grammatical range and accuracy"),
        ("PR", "Pronunciation"),
    ),
}
MIN_BANDS = 3
_STRICT = ConfigDict(extra="forbid")


class BandIn(BaseModel):
    model_config = _STRICT
    band: int = Field(ge=0, le=9)
    descriptor: str = Field(min_length=1, max_length=1000)


class CriterionIn(BaseModel):
    model_config = _STRICT
    code: str = Field(min_length=2, max_length=8)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    bands: list[BandIn] = Field(default_factory=list, max_length=10)


class SaveRubricIn(BaseModel):
    model_config = _STRICT
    revision: datetime
    title: str = Field(min_length=1, max_length=200)
    change_note: str | None = Field(default=None, max_length=2000)
    criteria: list[CriterionIn] = Field(max_length=4)


def rubric_issues(module: str, criteria: list[dict[str, Any]]) -> list[ValidationIssue]:
    """Publish-strictness checks. Structure errors block saving too."""
    issues: list[ValidationIssue] = []
    expected = [code for code, _ in CRITERIA[module]]
    codes = [c.get("code") for c in criteria]
    if sorted(c for c in codes if c) != sorted(expected) or len(codes) != len(expected):
        issues.append(
            error("rubric_criteria", "rubric", f"Criteria must be exactly {', '.join(expected)}.")
        )
    for c in criteria:
        where = f"rubric > {c.get('code')}"
        bands = [b["band"] for b in c.get("bands", [])]
        if len(bands) != len(set(bands)):
            issues.append(error("rubric_band_duplicate", where, "Each band once."))
        if not str(c.get("description", "")).strip():
            issues.append(error("rubric_description_missing", where, "Describe the criterion."))
        if len(set(bands)) < MIN_BANDS:
            issues.append(
                error(
                    "rubric_bands_missing",
                    where,
                    f"Write descriptors for at least {MIN_BANDS} bands.",
                )
            )
    return issues


def _structural(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return [i for i in issues if i.code in ("rubric_criteria", "rubric_band_duplicate")]


async def _load(session: AsyncSession, rubric_id: uuid.UUID) -> RubricVersion:
    rubric = await session.scalar(
        select(RubricVersion)
        .where(RubricVersion.id == rubric_id)
        .options(selectinload(RubricVersion.reviews))
        .execution_options(populate_existing=True)
    )
    if rubric is None:
        raise ContentNotFoundError(f"Rubric {rubric_id} not found.")
    return rubric


async def list_rubrics(session: AsyncSession, module: str) -> list[RubricVersion]:
    return list(
        await session.scalars(
            select(RubricVersion)
            .where(RubricVersion.module == module)
            .options(selectinload(RubricVersion.reviews))
            .order_by(RubricVersion.version_no.desc())
        )
    )


async def get_rubric(session: AsyncSession, rubric_id: uuid.UUID) -> RubricVersion:
    return await _load(session, rubric_id)


async def published_rubric(session: AsyncSession, module: str) -> RubricVersion | None:
    return await session.scalar(
        select(RubricVersion).where(
            RubricVersion.module == module, RubricVersion.status == "published"
        )
    )


def approved(rubric: RubricVersion) -> bool:
    return rubric.status == "in_review" and any(
        r.decision == ReviewDecision.APPROVED
        and (rubric.submitted_at is None or r.created_at >= rubric.submitted_at)
        and r.reviewer_id != rubric.created_by
        for r in rubric.reviews
    )


async def create_rubric(
    session: AsyncSession, module: str, *, actor_id: uuid.UUID
) -> RubricVersion:
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"rubric:{module}"))))
    open_one = await session.scalar(
        select(RubricVersion.id).where(
            RubricVersion.module == module, RubricVersion.status.in_(("draft", "in_review"))
        )
    )
    if open_one is not None:
        raise CatalogConflictError("A draft or in-review rubric already exists for this module.")
    latest = await session.scalar(
        select(RubricVersion)
        .where(RubricVersion.module == module)
        .order_by(RubricVersion.version_no.desc())
        .limit(1)
    )
    criteria = (
        [dict(c) for c in latest.criteria]
        if latest is not None
        else [
            {"code": code, "name": name, "description": "", "bands": []}
            for code, name in CRITERIA[module]
        ]
    )
    rubric = RubricVersion(
        module=module,
        version_no=(latest.version_no + 1) if latest else 1,
        title=latest.title if latest else f"{module.title()} assessment rubric",
        criteria=criteria,
        status="draft",
        created_by=actor_id,
    )
    session.add(rubric)
    await session.flush()
    await audit.record(
        session,
        actor_id=actor_id,
        action="content.rubric.create",
        entity_type="rubric_version",
        entity_id=rubric.id,
        changes={"module": module, "version_no": rubric.version_no},
    )
    return await _load(session, rubric.id)


async def save_rubric(
    session: AsyncSession, rubric_id: uuid.UUID, data: SaveRubricIn, *, actor_id: uuid.UUID
) -> tuple[RubricVersion, list[ValidationIssue]]:
    rubric = await _load(session, rubric_id)
    if rubric.status != "draft":
        raise ContentStateError("Only draft rubrics can be edited.")
    if rubric.updated_at != data.revision:
        raise DraftConflictError()
    criteria = [c.model_dump() for c in data.criteria]
    structural = _structural(rubric_issues(rubric.module, criteria))
    if structural:
        raise ContentValidationError(structural)
    rubric.title = data.title
    rubric.change_note = data.change_note
    rubric.criteria = criteria
    rubric.updated_at = func.now()
    await session.flush()
    await session.refresh(rubric, ["updated_at"])
    await audit.record(
        session,
        actor_id=actor_id,
        action="content.rubric.save_draft",
        entity_type="rubric_version",
        entity_id=rubric.id,
        changes={},
    )
    return await _load(session, rubric.id), rubric_issues(rubric.module, criteria)


async def submit_rubric(
    session: AsyncSession, rubric_id: uuid.UUID, *, actor_id: uuid.UUID
) -> RubricVersion:
    rubric = await _load(session, rubric_id)
    if rubric.status != "draft":
        raise ContentStateError("Only drafts can be submitted.")
    issues = rubric_issues(rubric.module, rubric.criteria)
    if has_errors(issues):
        raise ContentValidationError(issues)
    rubric.status = "in_review"
    rubric.submitted_at = datetime.now(UTC)
    await audit.record(
        session,
        actor_id=actor_id,
        action="content.rubric.submit",
        entity_type="rubric_version",
        entity_id=rubric.id,
        changes={},
    )
    await session.flush()
    return await _load(session, rubric.id)


async def review_rubric(
    session: AsyncSession,
    rubric_id: uuid.UUID,
    *,
    reviewer_id: uuid.UUID,
    decision: ReviewDecision,
    comment: str | None,
) -> RubricVersion:
    rubric = await _load(session, rubric_id)
    if rubric.status != "in_review":
        raise ContentStateError("Only rubrics in review can be reviewed.")
    if rubric.created_by is not None and rubric.created_by == reviewer_id:
        raise SelfReviewError()
    session.add(
        RubricReview(
            rubric_version_id=rubric.id,
            reviewer_id=reviewer_id,
            decision=decision.value,
            comment=comment,
            created_at=datetime.now(UTC),
        )
    )
    if decision is ReviewDecision.CHANGES_REQUESTED:
        rubric.status = "draft"
    await audit.record(
        session,
        actor_id=reviewer_id,
        action="content.rubric.review",
        entity_type="rubric_version",
        entity_id=rubric.id,
        changes={"decision": decision.value},
    )
    await session.flush()
    return await _load(session, rubric.id)


async def publish_rubric(
    session: AsyncSession, rubric_id: uuid.UUID, *, actor_id: uuid.UUID
) -> RubricVersion:
    rubric = await _load(session, rubric_id)
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(f"rubric:{rubric.module}")))
    )
    if rubric.status != "in_review":
        raise ContentStateError("Only rubrics in review can be published.")
    if not approved(rubric):
        raise ReviewRequiredError()
    previous = await published_rubric(session, rubric.module)
    if previous is not None:
        previous.status = "archived"
        await session.flush()
    rubric.status = "published"
    rubric.published_at = datetime.now(UTC)
    rubric.published_by = actor_id
    await audit.record(
        session,
        actor_id=actor_id,
        action="content.rubric.publish",
        entity_type="rubric_version",
        entity_id=rubric.id,
        changes={"archived": str(previous.id) if previous else None},
    )
    await session.flush()
    return await _load(session, rubric.id)


async def delete_rubric_draft(
    session: AsyncSession, rubric_id: uuid.UUID, *, actor_id: uuid.UUID
) -> None:
    rubric = await _load(session, rubric_id)
    if rubric.status != "draft":
        raise ContentStateError("Only drafts can be deleted.")
    await session.delete(rubric)
    await audit.record(
        session,
        actor_id=actor_id,
        action="content.rubric.delete_draft",
        entity_type="rubric_version",
        entity_id=rubric_id,
        changes={},
    )


@dataclass(frozen=True)
class RubricCriterionView:
    code: str
    name: str
    description: str
    bands: list[tuple[int, str]]


def criteria_view(rubric: RubricVersion) -> list[RubricCriterionView]:
    return [
        RubricCriterionView(
            code=c["code"],
            name=c["name"],
            description=c.get("description", ""),
            bands=[(b["band"], b["descriptor"]) for b in c.get("bands", [])],
        )
        for c in rubric.criteria
    ]
