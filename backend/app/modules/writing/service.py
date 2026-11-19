"""Candidate Writing: drafts with revision-guarded autosave, immutable submissions, and AI
evaluation as a background job (outbox topic `writing.evaluate`).

- One open draft per (user, task) (partial unique index); starting again returns it.
- Autosave carries a monotonically increasing `client_revision`; an older revision is refused
  (`stale_revision`) so a stale tab can never overwrite newer text.
- Submit is idempotent on its `Idempotency-Key`; it freezes the text (database trigger) and queues
  an evaluation in the same transaction.
- The evaluation job uses the published rubric and the configured provider. Without a provider or
  rubric it ends `unavailable` (retryable later); invalid input ends `rejected_input`. Bands are
  stored only from a validated `ielts_ai` result.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import structlog
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ai
from app.core.outbox import HandlerResult, OutboxContext, enqueue
from app.modules.content import api as content
from app.modules.writing.errors import (
    EvaluationNotRetryableError,
    StaleRevisionError,
    SubmissionLockedError,
    SubmissionNotFoundError,
    WritingTestUnavailableError,
)
from app.modules.writing.models import SubmissionStatus, WritingEvaluation, WritingSubmission
from app.shared.evaluation import RETRYABLE, EvaluationStatus
from app.shared.ids import new_id
from ielts_ai.graphs.evaluation import (
    EvaluationOutputError,
    RubricCriterion,
    WritingTaskInput,
    evaluate_writing,
)
from ielts_ai.guardrails.input import InputRejectedError, word_count
from ielts_ai.providers.gemini import GeminiError

log = structlog.get_logger(__name__)
TOPIC = "writing.evaluate"
MAX_EVAL_ATTEMPTS = 3
STALE_RUN = timedelta(minutes=15)
BAND_COLUMNS = {"TA": "band_task", "CC": "band_cc", "LR": "band_lr", "GRA": "band_gra"}


def _now() -> datetime:
    return datetime.now(UTC)


# ------------------------------------------------------------------------------ catalogue
async def published_tests(
    db: AsyncSession, *, search: str | None, difficulty: str | None
) -> list[Any]:
    return await content.delivery.published_listening_tests(
        db, search=search, difficulty=difficulty, module="writing"
    )


async def published_test(db: AsyncSession, test_id: uuid.UUID) -> tuple[Any, dict[str, Any]]:
    try:
        test = await content.delivery.published_listening_test(db, test_id, "writing")
        view = await content.productive.writing_student_view(db, test.version_id)
    except content.ContentNotFoundError as exc:
        raise WritingTestUnavailableError() from exc
    return test, view


async def task_image(db: AsyncSession, test_id: uuid.UUID, task_no: int) -> tuple[str, str]:
    test, _ = await published_test(db, test_id)
    try:
        return await content.productive.writing_task_image(db, test.version_id, task_no)
    except content.ContentNotFoundError as exc:
        raise WritingTestUnavailableError("No image is available for this task.") from exc


# ------------------------------------------------------------------------------ drafts
async def _owned(
    db: AsyncSession, user_id: uuid.UUID, submission_id: uuid.UUID, *, lock: bool = False
) -> WritingSubmission:
    query = select(WritingSubmission).where(
        WritingSubmission.id == submission_id, WritingSubmission.user_id == user_id
    )
    if lock:
        query = query.with_for_update()
    found = await db.scalar(query)
    if found is None:
        raise SubmissionNotFoundError()
    return found


async def start(
    db: AsyncSession, user_id: uuid.UUID, test_id: uuid.UUID, task_no: int
) -> WritingSubmission:
    """The candidate's open draft for the task, created (with a frozen task snapshot) if none."""
    test, _ = await published_test(db, test_id)
    try:
        ref = await content.productive.writing_task(db, test.version_id, task_no)
    except content.ContentNotFoundError as exc:
        raise WritingTestUnavailableError("This task is not available.") from exc
    query = select(WritingSubmission).where(
        WritingSubmission.user_id == user_id,
        WritingSubmission.writing_task_id == ref.task_id,
        WritingSubmission.status == SubmissionStatus.DRAFT.value,
    )
    existing = await db.scalar(query)
    if existing is not None:
        return existing
    snapshot = {**ref.snapshot, "test_id": str(test.test_id), "test_title": test.title}
    submission = WritingSubmission(
        user_id=user_id,
        test_version_id=test.version_id,
        writing_task_id=ref.task_id,
        task_no=ref.task_no,
        prompt_snapshot=snapshot,
    )
    try:
        async with db.begin_nested():
            db.add(submission)
            await db.flush()
        await db.refresh(submission)
    except IntegrityError:  # a concurrent start created it first
        found = await db.scalar(query)
        if found is None:
            raise
        return found
    return submission


async def get(db: AsyncSession, user_id: uuid.UUID, submission_id: uuid.UUID) -> WritingSubmission:
    return await _owned(db, user_id, submission_id)


def _apply_text(
    submission: WritingSubmission, body: str, client_revision: int, time_spent: int
) -> None:
    if submission.status != SubmissionStatus.DRAFT.value:
        raise SubmissionLockedError()
    if client_revision <= submission.client_revision:
        raise StaleRevisionError()
    submission.body = body
    submission.word_count = word_count(body)
    submission.client_revision = client_revision
    submission.time_spent_seconds = max(submission.time_spent_seconds, time_spent)


async def autosave(
    db: AsyncSession,
    user_id: uuid.UUID,
    submission_id: uuid.UUID,
    *,
    body: str,
    client_revision: int,
    time_spent_seconds: int,
) -> WritingSubmission:
    submission = await _owned(db, user_id, submission_id, lock=True)
    _apply_text(submission, body, client_revision, time_spent_seconds)
    await db.flush()
    await db.refresh(submission)
    return submission


async def submit(
    db: AsyncSession,
    user_id: uuid.UUID,
    submission_id: uuid.UUID,
    *,
    key: uuid.UUID,
    body: str,
    client_revision: int,
    time_spent_seconds: int,
) -> WritingSubmission:
    submission = await _owned(db, user_id, submission_id, lock=True)
    if submission.status == SubmissionStatus.SUBMITTED.value:
        if submission.submit_key == key:
            return submission  # retried request: same result
        raise SubmissionLockedError()
    if client_revision > submission.client_revision:
        _apply_text(submission, body, client_revision, time_spent_seconds)
    submission.status = SubmissionStatus.SUBMITTED.value
    submission.submit_key = key
    submission.submitted_at = _now()
    await db.flush()
    _queue(db, submission.id, key, user_id)
    await db.flush()
    await db.refresh(submission)
    return submission


def _queue(
    db: AsyncSession, submission_id: uuid.UUID, key: uuid.UUID, user_id: uuid.UUID
) -> WritingEvaluation:
    evaluation = WritingEvaluation(
        id=new_id(),
        submission_id=submission_id,
        status=EvaluationStatus.QUEUED.value,
        idempotency_key=key,
        requested_by=user_id,
    )
    db.add(evaluation)
    enqueue(db, TOPIC, {"evaluation_id": str(evaluation.id)})
    return evaluation


async def retry(
    db: AsyncSession, user_id: uuid.UUID, submission_id: uuid.UUID, *, key: uuid.UUID
) -> WritingEvaluation:
    submission = await _owned(db, user_id, submission_id, lock=True)
    same = await db.scalar(
        select(WritingEvaluation).where(
            WritingEvaluation.idempotency_key == key,
            WritingEvaluation.submission_id == submission.id,
        )
    )
    if same is not None:
        return same
    latest = await latest_evaluation(db, submission.id)
    if submission.status != SubmissionStatus.SUBMITTED.value or (
        latest is not None and latest.status not in RETRYABLE
    ):
        raise EvaluationNotRetryableError()
    evaluation = _queue(db, submission.id, key, user_id)
    await db.flush()
    await db.refresh(evaluation)
    return evaluation


async def latest_evaluation(db: AsyncSession, submission_id: uuid.UUID) -> WritingEvaluation | None:
    return await db.scalar(
        select(WritingEvaluation)
        .where(WritingEvaluation.submission_id == submission_id)
        .order_by(WritingEvaluation.created_at.desc(), WritingEvaluation.id.desc())
        .limit(1)
    )


async def history(
    db: AsyncSession, user_id: uuid.UUID, test_id: uuid.UUID | None = None
) -> list[tuple[WritingSubmission, WritingEvaluation | None]]:
    query = select(WritingSubmission).where(WritingSubmission.user_id == user_id)
    if test_id is not None:
        query = query.where(WritingSubmission.prompt_snapshot["test_id"].astext == str(test_id))
    rows = list(await db.scalars(query.order_by(WritingSubmission.created_at.desc()).limit(100)))
    return [(s, await latest_evaluation(db, s.id)) for s in rows]


async def model_answers(db: AsyncSession, submission: WritingSubmission) -> list[dict[str, Any]]:
    """Model answers are revealed only after the candidate has submitted (FR-WR-10)."""
    if submission.status != SubmissionStatus.SUBMITTED.value:
        return []
    return await content.productive.model_answers(
        db, submission.test_version_id, "writing", submission.task_no
    )


async def rubric_names(db: AsyncSession, rubric_id: uuid.UUID | None) -> dict[str, str]:
    if rubric_id is None:
        return {}
    rubric = await content.rubrics.get_rubric(db, rubric_id)
    return {c["code"]: c["name"] for c in rubric.criteria}


# ------------------------------------------------------------------------------ evaluation
@dataclass(frozen=True)
class _Job:
    evaluation_id: uuid.UUID
    task: WritingTaskInput
    response: str
    rubric_id: uuid.UUID | None
    rubric: list[RubricCriterion]


def _finish(
    evaluation: WritingEvaluation, status: EvaluationStatus, code: str | None, message: str | None
) -> None:
    evaluation.status = status.value
    evaluation.error_code = code
    evaluation.error_message = message
    evaluation.finished_at = _now()


async def _claim(db: AsyncSession, evaluation_id: uuid.UUID) -> _Job | None:
    evaluation = await db.scalar(
        select(WritingEvaluation).where(WritingEvaluation.id == evaluation_id).with_for_update()
    )
    if evaluation is None or evaluation.status not in (
        EvaluationStatus.QUEUED.value,
        EvaluationStatus.RUNNING.value,  # a crashed run is resumed
    ):
        return None
    # A long AI call can outlive the outbox lease: never run the same evaluation twice
    # concurrently. A run that started long ago is treated as crashed and resumed.
    if (
        evaluation.status == EvaluationStatus.RUNNING.value
        and evaluation.started_at is not None
        and evaluation.started_at > _now() - STALE_RUN
    ):
        return None
    submission = await db.get_one(WritingSubmission, evaluation.submission_id)
    rubric = await content.rubrics.published_rubric(db, "writing")
    evaluation.status = EvaluationStatus.RUNNING.value
    evaluation.attempt_count += 1
    evaluation.started_at = _now()
    evaluation.rubric_version_id = rubric.id if rubric else None
    snapshot = submission.prompt_snapshot
    return _Job(
        evaluation_id=evaluation.id,
        task=WritingTaskInput(
            task_no=submission.task_no,
            task_kind=str(snapshot.get("task_kind", "")),
            prompt_text=str(snapshot.get("prompt_text", "")),
            min_words=int(snapshot.get("min_words", 0)),
        ),
        response=submission.body,
        rubric_id=rubric.id if rubric else None,
        rubric=[
            RubricCriterion(c.code, c.name, c.description, c.bands)
            for c in content.rubrics.criteria_view(rubric)
        ]
        if rubric
        else [],
    )


async def handle_evaluate(ctx: OutboxContext, payload: dict[str, Any]) -> HandlerResult:
    evaluation_id = uuid.UUID(str(payload["evaluation_id"]))
    async with ctx.session_factory() as db, db.begin():
        job = await _claim(db, evaluation_id)
    if job is None:
        return "skipped"
    wired = ai.providers(ctx.settings)
    outcome: tuple[EvaluationStatus, str | None, str | None] | None = None
    result = None
    if wired.llm is None:
        outcome = (
            EvaluationStatus.UNAVAILABLE,
            "provider_not_configured",
            "AI evaluation is not available yet: no AI provider is configured.",
        )
    elif not job.rubric:
        outcome = (
            EvaluationStatus.UNAVAILABLE,
            "rubric_not_published",
            "AI evaluation is not available yet: no Writing rubric has been published.",
        )
    else:
        try:
            result = await evaluate_writing(
                wired.llm,
                task=job.task,
                response=job.response,
                rubric=job.rubric,
                correlation_id=str(job.evaluation_id),
                model_name=wired.llm_model,
            )
        except InputRejectedError as exc:
            outcome = (EvaluationStatus.REJECTED_INPUT, exc.code, str(exc))
        except (
            EvaluationOutputError,
            ValidationError,
            GeminiError,
            httpx.HTTPError,
            TimeoutError,
            OSError,
        ) as exc:
            log.warning(
                "writing.evaluate.failed",
                evaluation=str(job.evaluation_id),
                error=type(exc).__name__,
            )
            outcome = (EvaluationStatus.FAILED, "provider_error", type(exc).__name__)
    async with ctx.session_factory() as db, db.begin():
        evaluation = await db.get_one(WritingEvaluation, job.evaluation_id, with_for_update=True)
        if result is not None:
            for criterion in result.criteria:
                column = BAND_COLUMNS.get(criterion.code)
                if column:
                    setattr(evaluation, column, Decimal(str(criterion.band)))
            evaluation.band_overall = (
                Decimal(str(result.overall_band)) if result.overall_band is not None else None
            )
            evaluation.result = result.model_dump(mode="json")
            evaluation.provider = result.provider
            evaluation.model = result.model
            evaluation.prompt_version = result.prompt_version
            evaluation.prompt_hash = result.prompt_hash
            _finish(evaluation, EvaluationStatus.SUCCEEDED, None, None)
        elif outcome is not None:
            status, code, message = outcome
            if status is EvaluationStatus.FAILED and evaluation.attempt_count < MAX_EVAL_ATTEMPTS:
                evaluation.status = EvaluationStatus.QUEUED.value
                evaluation.error_code = code
                retry_later = True
            else:
                _finish(evaluation, status, code, message)
                retry_later = False
            if retry_later:
                enqueue(db, TOPIC, {"evaluation_id": str(evaluation.id)})
    return "sent"
