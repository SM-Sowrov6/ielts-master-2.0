"""Candidate Writing API under /api/v1/writing (owner-only submissions; another user's id answers
404). Unsafe methods are CSRF-protected by the identity middleware. Model answers appear only
after submission; evaluations come from the background job (never computed in the request)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.errors import PROBLEM_MEDIA_TYPE
from app.core.storage import PRESIGN_TTL_SECONDS
from app.modules.content import api as content
from app.modules.identity import api as identity
from app.modules.writing import service
from app.modules.writing.models import WritingSubmission
from app.modules.writing.schemas import (
    ImageUrlOut,
    SaveTextIn,
    StartIn,
    SubmissionOut,
    SubmissionSummaryOut,
    WritingTaskOut,
    WritingTestDetailOut,
    WritingTestOut,
)
from app.shared.evaluation import RETRYABLE
from app.shared.evaluation_schemas import ModelAnswerOut, evaluation_out

Db = Annotated[AsyncSession, Depends(get_db_session)]
User = Annotated[identity.CurrentUser, Depends(identity.current_user)]
IdempotencyKey = Annotated[uuid.UUID, Header(alias="Idempotency-Key")]


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _problems(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {c: {"description": "Problem", "content": {PROBLEM_MEDIA_TYPE: {}}} for c in codes}


router = APIRouter(
    prefix="/api/v1/writing",
    tags=["writing"],
    dependencies=[Depends(_no_store)],
    responses=_problems(401),
)


def _test(t: Any) -> WritingTestOut:
    return WritingTestOut(
        test_id=t.test_id,
        code=t.code,
        title=t.title,
        description=t.description,
        difficulty=t.difficulty,
        tags=t.tags,
        book_title=t.book_title,
        edition_label=t.edition_label,
        published_at=t.published_at,
    )


def _task(snapshot: dict[str, Any]) -> WritingTaskOut:
    return WritingTaskOut(**{k: snapshot[k] for k in WritingTaskOut.model_fields if k in snapshot})


async def _out(db: AsyncSession, s: WritingSubmission) -> SubmissionOut:
    evaluation = await service.latest_evaluation(db, s.id)
    names = await service.rubric_names(db, evaluation.rubric_version_id if evaluation else None)
    return SubmissionOut(
        id=s.id,
        test_id=uuid.UUID(str(s.prompt_snapshot["test_id"])),
        test_title=str(s.prompt_snapshot.get("test_title", "")),
        task_no=s.task_no,
        task=_task(s.prompt_snapshot),
        status=s.status,
        body=s.body,
        word_count=s.word_count,
        client_revision=s.client_revision,
        time_spent_seconds=s.time_spent_seconds,
        created_at=s.created_at,
        updated_at=s.updated_at,
        submitted_at=s.submitted_at,
        evaluation=evaluation_out(evaluation, names, evaluation.status in RETRYABLE)
        if evaluation
        else None,
        model_answers=[ModelAnswerOut(**a) for a in await service.model_answers(db, s)],
    )


def _summary(s: WritingSubmission, e: Any) -> SubmissionSummaryOut:
    return SubmissionSummaryOut(
        id=s.id,
        task_no=s.task_no,
        status=s.status,
        word_count=s.word_count,
        updated_at=s.updated_at,
        submitted_at=s.submitted_at,
        evaluation_status=e.status if e else None,
        band_overall=float(e.band_overall) if e and e.band_overall is not None else None,
    )


@router.get("/tests", response_model=list[WritingTestOut])
async def list_tests(
    db: Db,
    _: User,
    search: Annotated[str | None, Query(max_length=100)] = None,
    difficulty: content.Difficulty | None = None,
) -> list[WritingTestOut]:
    async with db.begin():
        rows = await service.published_tests(
            db, search=search, difficulty=difficulty.value if difficulty else None
        )
    return [_test(t) for t in rows]


@router.get("/tests/{test_id}", response_model=WritingTestDetailOut, responses=_problems(404))
async def get_test(test_id: uuid.UUID, db: Db, user: User) -> WritingTestDetailOut:
    async with db.begin():
        test, view = await service.published_test(db, test_id)
        mine = await service.history(db, user.id, test_id)
    return WritingTestDetailOut(
        test=_test(test),
        variant=view["variant"],
        tasks=[WritingTaskOut(**t) for t in view["tasks"]],
        submissions=[_summary(s, e) for s, e in mine],
    )


@router.get(
    "/tests/{test_id}/tasks/{task_no}/image",
    response_model=ImageUrlOut,
    responses=_problems(404, 503),
)
async def task_image(
    test_id: uuid.UUID, task_no: int, request: Request, db: Db, _: User
) -> ImageUrlOut:
    storage = content.media.playback_storage(request.app.state.settings)
    async with db.begin():
        key, mime = await service.task_image(db, test_id, task_no)
    url = await storage.presign_get(key, mime)
    return ImageUrlOut(url=url, expires_in_seconds=PRESIGN_TTL_SECONDS)


@router.post(
    "/submissions",
    response_model=SubmissionOut,
    status_code=status.HTTP_201_CREATED,
    responses=_problems(404),
)
async def start(body: StartIn, db: Db, user: User) -> SubmissionOut:
    async with db.begin():
        submission = await service.start(db, user.id, body.test_id, body.task_no)
        return await _out(db, submission)


@router.get("/submissions", response_model=list[SubmissionSummaryOut])
async def submissions(
    db: Db, user: User, test_id: uuid.UUID | None = None
) -> list[SubmissionSummaryOut]:
    async with db.begin():
        rows = await service.history(db, user.id, test_id)
    return [_summary(s, e) for s, e in rows]


@router.get("/submissions/{submission_id}", response_model=SubmissionOut, responses=_problems(404))
async def submission(submission_id: uuid.UUID, db: Db, user: User) -> SubmissionOut:
    async with db.begin():
        return await _out(db, await service.get(db, user.id, submission_id))


@router.put(
    "/submissions/{submission_id}", response_model=SubmissionOut, responses=_problems(404, 409)
)
async def autosave(submission_id: uuid.UUID, body: SaveTextIn, db: Db, user: User) -> SubmissionOut:
    async with db.begin():
        saved = await service.autosave(
            db,
            user.id,
            submission_id,
            body=body.body,
            client_revision=body.client_revision,
            time_spent_seconds=body.time_spent_seconds,
        )
        return await _out(db, saved)


@router.post(
    "/submissions/{submission_id}/submit",
    response_model=SubmissionOut,
    responses=_problems(404, 409),
)
async def submit(
    submission_id: uuid.UUID, body: SaveTextIn, db: Db, user: User, key: IdempotencyKey
) -> SubmissionOut:
    async with db.begin():
        done = await service.submit(
            db,
            user.id,
            submission_id,
            key=key,
            body=body.body,
            client_revision=body.client_revision,
            time_spent_seconds=body.time_spent_seconds,
        )
        return await _out(db, done)


@router.post(
    "/submissions/{submission_id}/evaluations",
    response_model=SubmissionOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_problems(404, 409),
)
async def retry(submission_id: uuid.UUID, db: Db, user: User, key: IdempotencyKey) -> SubmissionOut:
    """Queue a new evaluation after a failed or unavailable one."""
    async with db.begin():
        await service.retry(db, user.id, submission_id, key=key)
        return await _out(db, await service.get(db, user.id, submission_id))
