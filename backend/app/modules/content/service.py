"""Content versioning and publishing workflow (docs/CONTENT_MANAGEMENT_ARCHITECTURE.md §3).

draft -> in_review -> published -> archived; in_review -> draft (changes requested).
All functions run inside the caller's transaction (`async with session.begin(): ...`) and write
an audit entry for each state change. Actor IDs are plain UUIDs until users exist (Phase 3b).
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit import api as audit
from app.modules.content.enums import ReviewDecision, VersionStatus
from app.modules.content.errors import (
    ContentNotFoundError,
    ContentValidationError,
    InvalidTransitionError,
    OpenDraftExistsError,
    ReviewRequiredError,
    SelfReviewError,
)
from app.modules.content.models import (
    AnswerKey,
    AnswerVariant,
    BandConversionTable,
    Book,
    BookEdition,
    ContentLicence,
    ContentReview,
    Explanation,
    MediaAsset,
    Paragraph,
    Passage,
    Question,
    QuestionGroup,
    QuestionOption,
    SampleAnswer,
    Section,
    SpeakingPart,
    SpeakingQuestion,
    Test,
    TestModule,
    TestVersion,
    WritingTask,
)
from app.modules.content.question_types.base import ValidationIssue
from app.modules.content.tree import version_tree_options
from app.modules.content.validator import Stage, ValidationContext, has_errors, validate_version
from app.shared.ids import new_id


def _today() -> date:
    return datetime.now(UTC).date()


# ------------------------------------------------------------------------------------ loading
async def load_version_tree(session: AsyncSession, version_id: uuid.UUID) -> TestVersion:
    version = await session.scalar(
        select(TestVersion).where(TestVersion.id == version_id).options(*version_tree_options())
    )
    if version is None:
        raise ContentNotFoundError(f"Test version {version_id} not found.")
    return version


async def licence_for_test(session: AsyncSession, test_id: uuid.UUID) -> ContentLicence | None:
    return await session.scalar(
        select(ContentLicence)
        .join(Book, Book.license_id == ContentLicence.id)
        .join(BookEdition, BookEdition.book_id == Book.id)
        .join(Test, Test.edition_id == BookEdition.id)
        .where(Test.id == test_id)
    )


def referenced_asset_ids(version: TestVersion) -> set[uuid.UUID]:
    ids: set[uuid.UUID] = set()
    for module in version.modules:
        for section in module.sections:
            if section.audio_asset_id:
                ids.add(section.audio_asset_id)
            ids.update(g.image_asset_id for g in section.groups if g.image_asset_id)
        ids.update(t.image_asset_id for t in module.writing_tasks if t.image_asset_id)
    return ids


async def build_validation_context(
    session: AsyncSession,
    version: TestVersion,
    *,
    stage: Stage,
    licence: ContentLicence | None,
) -> ValidationContext:
    asset_ids = referenced_asset_ids(version)
    assets = (
        {
            a.id: a
            for a in await session.scalars(select(MediaAsset).where(MediaAsset.id.in_(asset_ids)))
        }
        if asset_ids
        else {}
    )
    band_rows = await session.execute(
        select(BandConversionTable.module, BandConversionTable.variant).where(
            BandConversionTable.is_default
        )
    )
    return ValidationContext(
        today=_today(),
        stage=stage,
        licence=licence,
        assets=assets,
        band_tables=frozenset((m, v) for m, v in band_rows.all()),
    )


async def validate_persisted_version(
    session: AsyncSession, version: TestVersion, stage: Stage
) -> list[ValidationIssue]:
    licence = await licence_for_test(session, version.test_id)
    context = await build_validation_context(session, version, stage=stage, licence=licence)
    return validate_version(version, context)


# ------------------------------------------------------------------------------------ drafts
async def _lock_test(session: AsyncSession, test_id: uuid.UUID) -> Test:
    test = await session.scalar(select(Test).where(Test.id == test_id).with_for_update())
    if test is None:
        raise ContentNotFoundError(f"Test {test_id} not found.")
    return test


async def open_version_exists(session: AsyncSession, test_id: uuid.UUID) -> bool:
    found = await session.scalar(
        select(TestVersion.id).where(
            TestVersion.test_id == test_id,
            TestVersion.status.in_([VersionStatus.DRAFT, VersionStatus.IN_REVIEW]),
        )
    )
    return found is not None


async def next_version_no(session: AsyncSession, test_id: uuid.UUID) -> int:
    current = await session.scalar(
        select(func.max(TestVersion.version_no)).where(TestVersion.test_id == test_id)
    )
    return (current or 0) + 1


async def create_next_draft(
    session: AsyncSession,
    test_id: uuid.UUID,
    *,
    actor_id: uuid.UUID,
    change_note: str | None = None,
) -> TestVersion:
    """New draft for a test: a deep copy of the current published version (or the latest version),
    or an empty draft if the test has no versions. `questions.lineage_id` is preserved."""
    test = await _lock_test(session, test_id)
    if await open_version_exists(session, test_id):
        raise OpenDraftExistsError()
    source_id = test.current_published_version_id or await session.scalar(
        select(TestVersion.id)
        .where(TestVersion.test_id == test_id)
        .order_by(TestVersion.version_no.desc())
        .limit(1)
    )
    version_no = await next_version_no(session, test_id)
    if source_id is None:
        draft = TestVersion(test_id=test_id, version_no=version_no, created_by=actor_id)
    else:
        draft = clone_version(await load_version_tree(session, source_id), version_no, actor_id)
    draft.change_note = change_note
    session.add(draft)
    await session.flush()
    await audit.record(
        session,
        actor_id=actor_id,
        action="content.test_version.create_draft",
        entity_type="test_version",
        entity_id=draft.id,
        changes={
            "test_id": str(test_id),
            "version_no": version_no,
            "copied_from": str(source_id) if source_id else None,
        },
    )
    return draft


def _clone_samples(samples: list[SampleAnswer]) -> list[SampleAnswer]:
    return [
        SampleAnswer(band=a.band, body=a.body, license_id=a.license_id, author_note=a.author_note)
        for a in samples
    ]


def clone_version(source: TestVersion, version_no: int, actor_id: uuid.UUID) -> TestVersion:
    """Deep copy of a fully loaded version tree with new IDs (lineage preserved)."""
    paragraph_ids: dict[uuid.UUID, uuid.UUID] = {}

    def clone_paragraph(p: Paragraph) -> Paragraph:
        new = Paragraph(
            id=new_id(), label=p.label, sort_order=p.sort_order, plain_text=p.plain_text
        )
        paragraph_ids[p.id] = new.id
        return new

    def clone_option(o: QuestionOption) -> QuestionOption:
        return QuestionOption(label=o.label, text=o.text, sort_order=o.sort_order)

    def clone_question(q: Question) -> Question:
        explanation = q.explanation
        return Question(
            lineage_id=q.lineage_id,
            number_from=q.number_from,
            number_to=q.number_to,
            marks=q.marks,
            stem=q.stem,
            config=dict(q.config),
            difficulty=q.difficulty,
            tags=list(q.tags),
            options=[clone_option(o) for o in q.options],
            answer_keys=[
                AnswerKey(
                    slot=k.slot,
                    canonical_value=k.canonical_value,
                    notation=k.notation,
                    match_mode=k.match_mode,
                    variants=[AnswerVariant(value=v.value) for v in k.variants],
                )
                for k in q.answer_keys
            ],
            explanation=(
                Explanation(
                    body=explanation.body,
                    evidence_paragraph_id=(
                        paragraph_ids.get(explanation.evidence_paragraph_id)
                        if explanation.evidence_paragraph_id
                        else None
                    ),
                    audio_start_ms=explanation.audio_start_ms,
                    audio_end_ms=explanation.audio_end_ms,
                )
                if explanation is not None
                else None
            ),
        )

    def clone_section(s: Section) -> Section:
        # Passages (and paragraph ids) first, so explanations can remap their evidence links.
        passages = [
            Passage(
                sort_order=p.sort_order,
                title=p.title,
                body_format=p.body_format,
                body=p.body,
                word_count=p.word_count,
                paragraphs=[clone_paragraph(par) for par in p.paragraphs],
            )
            for p in s.passages
        ]
        return Section(
            section_no=s.section_no,
            title=s.title,
            instructions=s.instructions,
            context=s.context,
            audio_asset_id=s.audio_asset_id,
            duration_seconds=s.duration_seconds,
            passages=passages,
            groups=[
                QuestionGroup(
                    question_type=g.question_type,
                    instructions=g.instructions,
                    config=dict(g.config),
                    image_asset_id=g.image_asset_id,
                    sort_order=g.sort_order,
                    options=[clone_option(o) for o in g.options],
                    questions=[clone_question(q) for q in g.questions],
                )
                for g in s.groups
            ],
        )

    return TestVersion(
        test_id=source.test_id,
        version_no=version_no,
        created_by=actor_id,
        description=source.description,
        difficulty=source.difficulty,
        tags=list(source.tags),
        modules=[
            TestModule(
                module=m.module,
                variant=m.variant,
                duration_seconds=m.duration_seconds,
                sort_order=m.sort_order,
                sections=[clone_section(s) for s in m.sections],
                writing_tasks=[
                    WritingTask(
                        task_no=t.task_no,
                        task_kind=t.task_kind,
                        prompt=t.prompt,
                        image_asset_id=t.image_asset_id,
                        min_words=t.min_words,
                        key_features=list(t.key_features),
                        sample_answers=_clone_samples(t.sample_answers),
                    )
                    for t in m.writing_tasks
                ],
                speaking_parts=[
                    SpeakingPart(
                        part_no=p.part_no,
                        topic=p.topic,
                        cue_card=p.cue_card,
                        questions=[
                            SpeakingQuestion(
                                text=q.text, sort_order=q.sort_order, is_follow_up=q.is_follow_up
                            )
                            for q in p.questions
                        ],
                        sample_answers=_clone_samples(p.sample_answers),
                    )
                    for p in m.speaking_parts
                ],
            )
            for m in source.modules
        ],
    )


# ------------------------------------------------------------------------------------ workflow
def _require_status(version: TestVersion, *allowed: VersionStatus) -> None:
    if version.status not in allowed:
        raise InvalidTransitionError(
            f"Version is {version.status}; expected {', '.join(s.value for s in allowed)}."
        )


async def submit_for_review(
    session: AsyncSession, version_id: uuid.UUID, *, actor_id: uuid.UUID
) -> list[ValidationIssue]:
    """Validate at publish strictness and move draft -> in_review. Returns remaining warnings."""
    version = await load_version_tree(session, version_id)
    _require_status(version, VersionStatus.DRAFT)
    issues = await validate_persisted_version(session, version, "publish")
    if has_errors(issues):
        raise ContentValidationError(issues)
    version.status = VersionStatus.IN_REVIEW
    version.submitted_at = datetime.now(UTC)
    await audit.record(
        session,
        actor_id=actor_id,
        action="content.test_version.submit",
        entity_type="test_version",
        entity_id=version.id,
        changes={"warnings": len(issues)},
    )
    return issues


async def review_version(
    session: AsyncSession,
    version_id: uuid.UUID,
    *,
    reviewer_id: uuid.UUID,
    decision: ReviewDecision,
    comment: str | None = None,
) -> ContentReview:
    """Four-eyes review: the author of a version cannot review it."""
    version = await load_version_tree(session, version_id)
    _require_status(version, VersionStatus.IN_REVIEW)
    if version.created_by is not None and version.created_by == reviewer_id:
        raise SelfReviewError()
    review = ContentReview(
        test_version_id=version.id,
        reviewer_id=reviewer_id,
        decision=decision.value,
        comment=comment,
        created_at=datetime.now(UTC),
    )
    session.add(review)
    if decision is ReviewDecision.CHANGES_REQUESTED:
        version.status = VersionStatus.DRAFT
    await audit.record(
        session,
        actor_id=reviewer_id,
        action="content.test_version.review",
        entity_type="test_version",
        entity_id=version.id,
        changes={"decision": decision.value},
    )
    await session.flush()
    return review


async def publish_version(
    session: AsyncSession, version_id: uuid.UUID, *, actor_id: uuid.UUID
) -> TestVersion:
    """in_review -> published, archiving the previous published version in the same transaction."""
    version = await load_version_tree(session, version_id)
    test = await _lock_test(session, version.test_id)
    _require_status(version, VersionStatus.IN_REVIEW)
    submitted = version.submitted_at
    approved = [
        r
        for r in version.reviews
        if r.decision == ReviewDecision.APPROVED
        and (submitted is None or r.created_at >= submitted)
        and r.reviewer_id != version.created_by
    ]
    if not approved:
        raise ReviewRequiredError()
    issues = await validate_persisted_version(session, version, "publish")
    if has_errors(issues):
        raise ContentValidationError(issues)

    previous_id = test.current_published_version_id
    if previous_id is not None:
        previous = await session.get_one(TestVersion, previous_id)
        previous.status = VersionStatus.ARCHIVED
        await session.flush()  # free the "one published per test" slot before claiming it
    now = datetime.now(UTC)
    version.status = VersionStatus.PUBLISHED
    version.published_at = now
    version.published_by = actor_id
    await session.flush()
    test.current_published_version_id = version.id
    await audit.record(
        session,
        actor_id=actor_id,
        action="content.test_version.publish",
        entity_type="test_version",
        entity_id=version.id,
        changes={"archived": str(previous_id) if previous_id else None},
    )
    await session.flush()
    return version


async def unpublish_version(
    session: AsyncSession, version_id: uuid.UUID, *, actor_id: uuid.UUID
) -> None:
    """published -> archived without a successor; the test leaves the library."""
    version = await session.get(TestVersion, version_id)
    if version is None:
        raise ContentNotFoundError(f"Test version {version_id} not found.")
    test = await _lock_test(session, version.test_id)
    _require_status(version, VersionStatus.PUBLISHED)
    version.status = VersionStatus.ARCHIVED
    test.current_published_version_id = None
    await audit.record(
        session,
        actor_id=actor_id,
        action="content.test_version.unpublish",
        entity_type="test_version",
        entity_id=version.id,
    )
    await session.flush()
