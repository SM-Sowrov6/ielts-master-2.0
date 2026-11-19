"""Candidate Listening API (docs/API_SPECIFICATION.md §4; EXAMINATION_ENGINE_DESIGN.md).

`/api/v1/listening/*` is owned by exams: the practice catalogue joins published content with the
candidate's own attempts, which the content module must not read. `/api/v1/attempts/*` are
owner-only (another user's attempt answers 404). Unsafe methods are CSRF-protected by the identity
middleware; answer writes additionally need the writer lease (`X-Writer-Token`).
Answer keys appear only in `/attempts/{id}/review`, after completion.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import get_db_session
from app.core.errors import PROBLEM_MEDIA_TYPE
from app.modules.content import api as content
from app.modules.exams import service
from app.modules.exams.errors import AttemptStateError, TestUnavailableError
from app.modules.exams.models import AttemptStatus, ExamAttempt
from app.modules.exams.schemas import (
    AnswersOut,
    AttemptOut,
    AttemptReviewOut,
    AttemptTestOut,
    AudioOut,
    CreateAttemptIn,
    ExamModule,
    HistoryOut,
    ImageOut,
    LeaseOut,
    ListeningTestDetailOut,
    ListeningTestOut,
    ModeRulesOut,
    ResultOut,
    ReviewItemOut,
    SaveAnswersIn,
    SaveAnswersOut,
    SectionBreakdownOut,
    SectionSummaryOut,
    StoredAnswerOut,
    SubmitIn,
    TestAttemptSummary,
    TypeBreakdownOut,
)
from app.modules.identity import api as identity

Db = Annotated[AsyncSession, Depends(get_db_session)]
User = Annotated[identity.CurrentUser, Depends(identity.current_user)]
WriterToken = Annotated[str, Header(alias="X-Writer-Token", min_length=10, max_length=200)]
IdempotencyKey = Annotated[uuid.UUID, Header(alias="Idempotency-Key")]


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _problems(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {c: {"description": "Problem", "content": {PROBLEM_MEDIA_TYPE: {}}} for c in codes}


router = APIRouter(
    prefix="/api/v1",
    tags=["listening"],
    dependencies=[Depends(_no_store)],
    responses=_problems(401),
)


def _now() -> datetime:
    return datetime.now(UTC)


def _attempt(a: ExamAttempt, **extra: Any) -> AttemptOut:
    rules = service.rules_of(a)
    return AttemptOut(
        id=a.id,
        module=service.module_of(a),
        test_id=a.test_id,
        mode=a.mode,
        status=a.status,
        test=AttemptTestOut(**a.config_snapshot["test"]),
        started_at=a.started_at,
        deadline_at=a.deadline_at,
        submitted_at=a.submitted_at,
        completed_at=a.completed_at,
        submitted_by=a.submitted_by,
        server_now=_now(),
        writer_epoch=a.writer_epoch,
        questions_total=sum(int(i["marks"]) for i in service.manifest(a)),
        rules={
            k: rules[k] for k in ("timing", "listening", "submission", "navigation") if k in rules
        },
        **extra,
    )


def _mode_rules(mode: str, rules: dict[str, Any]) -> ModeRulesOut:
    timing = rules["timing"]
    listening = rules.get("listening", {})
    return ModeRulesOut(
        mode=mode,
        timed=bool(timing.get("enforce")),
        time_limit_seconds=service.time_limit_seconds(timing),
        max_plays=listening.get("max_plays"),
        allow_seek=bool(listening.get("allow_seek", True)),
        auto_submit=bool(rules["submission"].get("auto_submit_on_deadline")),
    )


def _test_out(
    t: Any, stats: dict[str, Any] | None, open_attempt: ExamAttempt | None
) -> dict[str, Any]:
    return {
        "test_id": t.test_id,
        "code": t.code,
        "title": t.title,
        "description": t.description,
        "difficulty": t.difficulty,
        "tags": t.tags,
        "duration_seconds": t.duration_seconds,
        "book_title": t.book_title,
        "edition_label": t.edition_label,
        "locked": t.is_premium,
        "sections": t.sections,
        "questions": t.questions,
        "published_at": t.published_at,
        "progress": TestAttemptSummary(
            completed=(stats or {}).get("completed", 0),
            best_raw=(stats or {}).get("best_raw"),
            last_completed_at=(stats or {}).get("last_completed_at"),
            open_attempt_id=open_attempt.id if open_attempt else None,
            open_attempt_mode=open_attempt.mode if open_attempt else None,
        ),
    }


# ------------------------------------------------------------------------------ catalogue
@router.get("/{module}/tests", response_model=list[ListeningTestOut])
async def listening_tests(
    module: ExamModule,
    db: Db,
    user: User,
    search: Annotated[str | None, Query(max_length=100)] = None,
    difficulty: Annotated[str | None, Query(pattern="^(easy|medium|hard)$")] = None,
) -> list[ListeningTestOut]:
    async with db.begin():
        tests = await content.delivery.published_listening_tests(
            db, search=search, difficulty=difficulty, module=module
        )
        stats = await service.attempt_stats_by_test(db, user.id)
        open_attempts = await service.open_attempts_by_test(db, user.id)
    return [
        ListeningTestOut(**_test_out(t, stats.get(t.test_id), open_attempts.get(t.test_id)))
        for t in tests
    ]


@router.get(
    "/{module}/tests/{test_id}", response_model=ListeningTestDetailOut, responses=_problems(404)
)
async def listening_test(
    module: ExamModule, test_id: uuid.UUID, db: Db, user: User
) -> ListeningTestDetailOut:
    async with db.begin():
        try:
            t = await content.delivery.published_listening_test(db, test_id, module)
        except content.ContentNotFoundError as exc:
            raise TestUnavailableError() from exc
        sections = await content.delivery.listening_sections(db, t.version_id)
        stats = await service.attempt_stats_by_test(db, user.id)
        open_attempts = await service.open_attempts_by_test(db, user.id)
        modes, default_mode, rules = await service.template_modes(db, module)
        rows = await service.history(db, user.id, test_id=test_id, limit=20)
    return ListeningTestDetailOut(
        **_test_out(t, stats.get(t.test_id), open_attempts.get(t.test_id)),
        section_list=[SectionSummaryOut(**s.__dict__) for s in sections],
        modes=[_mode_rules(m, rules[m]) for m in modes],
        default_mode=default_mode,
        attempts=[
            _attempt(
                r.attempt,
                answered=r.answered,
                raw_score=r.raw_score,
                max_score=r.max_score,
                band_estimate=r.band_estimate,
            )
            for r in rows
        ],
    )


# ------------------------------------------------------------------------------ attempts
@router.post(
    "/attempts",
    response_model=AttemptOut,
    status_code=status.HTTP_201_CREATED,
    responses=_problems(403, 404, 409, 422),
)
async def create_attempt(
    body: CreateAttemptIn, db: Db, user: User, idempotency_key: IdempotencyKey
) -> AttemptOut:
    async with db.begin():
        attempt = await service.create_attempt(
            db,
            user_id=user.id,
            test_id=body.test_id,
            mode=body.mode,
            idempotency_key=idempotency_key,
            module=body.module,
        )
        return _attempt(attempt)


@router.get("/attempts", response_model=HistoryOut)
async def attempts(
    db: Db,
    user: User,
    test_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    module: ExamModule | None = None,
) -> HistoryOut:
    async with db.begin():
        rows = await service.history(db, user.id, test_id=test_id, limit=limit, module=module)
    return HistoryOut(
        items=[
            _attempt(
                r.attempt,
                answered=r.answered,
                raw_score=r.raw_score,
                max_score=r.max_score,
                band_estimate=r.band_estimate,
            )
            for r in rows
        ]
    )


@router.get("/attempts/{attempt_id}", response_model=AttemptOut, responses=_problems(404))
async def get_attempt(attempt_id: uuid.UUID, db: Db, user: User) -> AttemptOut:
    async with db.begin():
        attempt = await service.get_attempt(db, user.id, attempt_id)
        answered = sum(1 for a in await service.stored_answers(db, attempt.id) if a.response)
        return _attempt(attempt, answered=answered)


@router.post("/attempts/{attempt_id}/start", response_model=LeaseOut, responses=_problems(404, 409))
async def start(attempt_id: uuid.UUID, db: Db, user: User) -> LeaseOut:
    async with db.begin():
        attempt, lease = await service.start_attempt(db, user.id, attempt_id)
        return LeaseOut(
            attempt=_attempt(attempt, answered=0),
            writer_epoch=lease.epoch,
            writer_token=lease.token,
        )


@router.post(
    "/attempts/{attempt_id}/resume", response_model=LeaseOut, responses=_problems(404, 409)
)
async def resume(attempt_id: uuid.UUID, db: Db, user: User) -> LeaseOut:
    """Continue on this device/tab: issues a new lease; older leases can no longer write."""
    async with db.begin():
        attempt, lease = await service.resume_attempt(db, user.id, attempt_id)
        answered = sum(1 for a in await service.stored_answers(db, attempt.id) if a.response)
        return LeaseOut(
            attempt=_attempt(attempt, answered=answered),
            writer_epoch=lease.epoch,
            writer_token=lease.token,
        )


@router.get("/attempts/{attempt_id}/content", responses=_problems(404))
async def attempt_content(attempt_id: uuid.UUID, db: Db, user: User) -> dict[str, Any]:
    """Key-stripped content of the pinned version (handler student views only)."""
    async with db.begin():
        attempt = await service.get_attempt(db, user.id, attempt_id)
        return await content.delivery.listening_student_view(db, attempt.test_version_id)


@router.get("/attempts/{attempt_id}/answers", response_model=AnswersOut, responses=_problems(404))
async def answers(attempt_id: uuid.UUID, db: Db, user: User) -> AnswersOut:
    async with db.begin():
        attempt = await service.get_attempt(db, user.id, attempt_id)
        stored = await service.stored_answers(db, attempt.id)
    return AnswersOut(answers=[StoredAnswerOut(**s.__dict__) for s in stored], server_now=_now())


@router.put(
    "/attempts/{attempt_id}/answers",
    response_model=SaveAnswersOut,
    responses=_problems(403, 404, 409, 422),
)
async def save_answers(
    attempt_id: uuid.UUID, body: SaveAnswersIn, db: Db, user: User, writer_token: WriterToken
) -> SaveAnswersOut:
    async with db.begin():
        attempt, stored = await service.save_answers(
            db,
            user_id=user.id,
            attempt_id=attempt_id,
            writer_epoch=body.writer_epoch,
            writer_token=writer_token,
            answers=[
                service.AnswerIn(a.question_id, a.response, a.client_revision, a.flagged)
                for a in body.answers
            ],
        )
    return SaveAnswersOut(
        stored=[StoredAnswerOut(**s.__dict__) for s in stored],
        server_now=_now(),
        deadline_at=attempt.deadline_at,
    )


@router.post(
    "/attempts/{attempt_id}/sections/{section_no}/audio-url",
    response_model=AudioOut,
    responses=_problems(404, 409, 503),
)
async def audio_url(
    attempt_id: uuid.UUID,
    section_no: Annotated[int, Path(ge=1, le=4)],
    request: Request,
    db: Db,
    user: User,
) -> AudioOut:
    settings: Settings = request.app.state.settings
    storage = content.media.playback_storage(settings)
    async with db.begin():
        grant = await service.audio_grant(db, user.id, attempt_id, section_no)
    url = await storage.presign_get(
        grant.storage_key, grant.mime_type, ttl_seconds=grant.ttl_seconds
    )
    return AudioOut(
        url=url,
        expires_in_seconds=grant.ttl_seconds,
        offset_ms=grant.offset_ms,
        allow_seek=grant.allow_seek,
        max_plays=grant.max_plays,
        plays_used=grant.plays_used,
    )


@router.get(
    "/attempts/{attempt_id}/sections/{section_no}/groups/{group_no}/image-url",
    response_model=ImageOut,
    responses=_problems(404, 503),
)
async def image_url(
    attempt_id: uuid.UUID,
    section_no: Annotated[int, Path(ge=1, le=4)],
    group_no: Annotated[int, Path(ge=1, le=50)],
    request: Request,
    db: Db,
    user: User,
) -> ImageOut:
    """Short-lived URL of a map/plan/diagram image of the owner's attempt."""
    storage = content.media.playback_storage(request.app.state.settings)
    async with db.begin():
        key, mime, ttl = await service.image_grant(db, user.id, attempt_id, section_no, group_no)
    url = await storage.presign_get(key, mime, ttl_seconds=ttl)
    return ImageOut(url=url, expires_in_seconds=ttl)


@router.post(
    "/attempts/{attempt_id}/submit",
    response_model=AttemptOut,
    responses=_problems(403, 404, 409, 422),
)
async def submit(
    attempt_id: uuid.UUID,
    body: SubmitIn,
    db: Db,
    user: User,
    idempotency_key: IdempotencyKey,
    writer_token: WriterToken,
) -> AttemptOut:
    async with db.begin():
        attempt = await service.submit_attempt(
            db,
            user_id=user.id,
            attempt_id=attempt_id,
            idempotency_key=idempotency_key,
            writer_epoch=body.writer_epoch,
            writer_token=writer_token,
            final_answers=[
                service.AnswerIn(a.question_id, a.response, a.client_revision, a.flagged)
                for a in body.final_answers
            ],
        )
        return _attempt(attempt)


@router.get(
    "/attempts/{attempt_id}/result", response_model=ResultOut, responses=_problems(404, 409)
)
async def result(attempt_id: uuid.UUID, db: Db, user: User) -> ResultOut:
    async with db.begin():
        r = await service.result(db, user.id, attempt_id)
    correct = sum(s["correct"] for s in r.sections)
    questions = sum(s["questions"] for s in r.sections)
    unanswered = sum(s["unanswered"] for s in r.sections)
    return ResultOut(
        attempt=_attempt(
            r.attempt, raw_score=r.raw_score, max_score=r.max_score, band_estimate=r.band_estimate
        ),
        raw_score=r.raw_score,
        max_score=r.max_score,
        percentage=round(100 * r.raw_score / r.max_score, 1) if r.max_score else 0.0,
        correct=correct,
        incorrect=questions - correct - unanswered,
        unanswered=unanswered,
        band_estimate=r.band_estimate,
        band_available=r.band_estimate is not None,
        sections=[SectionBreakdownOut(**s) for s in r.sections],
        question_types=[TypeBreakdownOut(**s) for s in r.question_types],
    )


@router.get(
    "/attempts/{attempt_id}/review", response_model=AttemptReviewOut, responses=_problems(404, 409)
)
async def review(attempt_id: uuid.UUID, db: Db, user: User) -> AttemptReviewOut:
    """Correct answers and explanations: owner only, and only after the attempt is completed."""
    async with db.begin():
        items = await service.review(db, user.id, attempt_id)
        attempt = await service.get_attempt(db, user.id, attempt_id)
        if attempt.status != AttemptStatus.COMPLETED:  # pragma: no cover - checked in service
            raise AttemptStateError(attempt.status)
        view = await content.delivery.listening_student_view(db, attempt.test_version_id)
    return AttemptReviewOut(
        attempt=_attempt(attempt),
        items=[ReviewItemOut(**{k: v for k, v in i.items() if k != "section_id"}) for i in items],
        content=view,
    )
