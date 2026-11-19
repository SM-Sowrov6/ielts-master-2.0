"""Candidate Speaking API under /api/v1/speaking (owner-only sessions; another user's id answers
404). Audio goes browser -> private object storage via presigned PUT and is verified here before
it counts. Evaluations come from the background job; scores are never computed in the request."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.errors import PROBLEM_MEDIA_TYPE
from app.core.storage import PRESIGN_TTL_SECONDS
from app.modules.content import api as content
from app.modules.identity import api as identity
from app.modules.speaking import service
from app.modules.speaking.errors import RecordingRejectedError
from app.modules.speaking.models import SpeakingSession
from app.shared.evaluation import RETRYABLE
from app.shared.evaluation_schemas import EvaluationOut, ModelAnswerOut, evaluation_out

Db = Annotated[AsyncSession, Depends(get_db_session)]
User = Annotated[identity.CurrentUser, Depends(identity.current_user)]
IdempotencyKey = Annotated[uuid.UUID, Header(alias="Idempotency-Key")]
_STRICT = ConfigDict(extra="forbid")


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _problems(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {c: {"description": "Problem", "content": {PROBLEM_MEDIA_TYPE: {}}} for c in codes}


router = APIRouter(
    prefix="/api/v1/speaking",
    tags=["speaking"],
    dependencies=[Depends(_no_store)],
    responses=_problems(401),
)


# ------------------------------------------------------------------------------ schemas
class SpeakingTestOut(BaseModel):
    test_id: uuid.UUID
    code: str
    title: str
    description: str | None
    difficulty: str | None
    tags: list[str]
    book_title: str
    published_at: datetime | None


class CueCardOut(BaseModel):
    prompt: str
    points: list[str] = []
    closing: str | None = None


class PartOut(BaseModel):
    part_no: int
    topic: str
    cue_card: CueCardOut | None
    questions: list[str]
    prep_seconds: int
    answer_seconds: int


class SessionSummaryOut(BaseModel):
    id: uuid.UUID
    test_id: uuid.UUID | None
    mode: str
    status: Literal["recording", "submitted"]
    created_at: datetime
    submitted_at: datetime | None
    evaluation_status: str | None
    band_overall: float | None


class SpeakingTestDetailOut(BaseModel):
    test: SpeakingTestOut
    parts: list[PartOut]
    consent_version: str


class StartSessionIn(BaseModel):
    model_config = _STRICT
    test_id: uuid.UUID
    mode: Literal["full", "part1", "part2", "part3"] = "full"
    # Both consents must be given explicitly; they are stored with their document version.
    voice_processing_consent: Literal[True]
    audio_recording_consent: Literal[True]


class ItemOut(BaseModel):
    part_no: int
    question_no: int
    text: str
    cue_card: CueCardOut | None
    prep_seconds: int
    answer_seconds: int
    recording_id: uuid.UUID | None
    recording_status: str | None
    duration_ms: int | None
    transcript: str | None


class SessionOut(BaseModel):
    id: uuid.UUID
    test_title: str
    mode: str
    status: Literal["recording", "submitted"]
    created_at: datetime
    submitted_at: datetime | None
    audio_purge_after: datetime | None
    items: list[ItemOut]
    evaluation: EvaluationOut | None
    model_answers: list[ModelAnswerOut]


class RecordingIn(BaseModel):
    model_config = _STRICT
    part_no: Literal[1, 2, 3]
    question_no: int = Field(ge=1, le=30)
    mime_type: str = Field(min_length=5, max_length=100)
    size_bytes: int = Field(gt=0, le=service.MAX_RECORDING_BYTES)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    duration_ms: int = Field(gt=0, le=900_000)


class RecordingTicketOut(BaseModel):
    recording_id: uuid.UUID
    upload_url: str
    method: Literal["PUT"] = "PUT"
    headers: dict[str, str]
    expires_in_seconds: int


class RecordingOut(BaseModel):
    id: uuid.UUID
    status: str


class AudioUrlOut(BaseModel):
    url: str
    expires_in_seconds: int


# ------------------------------------------------------------------------------ helpers
def _test(t: Any) -> SpeakingTestOut:
    return SpeakingTestOut(
        test_id=t.test_id,
        code=t.code,
        title=t.title,
        description=t.description,
        difficulty=t.difficulty,
        tags=t.tags,
        book_title=t.book_title,
        published_at=t.published_at,
    )


def _card(card: Any) -> CueCardOut | None:
    return CueCardOut.model_validate(card) if card else None


async def _session(db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID) -> SessionOut:
    session, items, recordings, _ = await service.session_detail(db, user_id, session_id)
    by_item = {(r.part_no, r.question_no): r for r in recordings}
    evaluation = await service.latest_evaluation(db, session.id)
    names = await service.rubric_names(db, evaluation.rubric_version_id if evaluation else None)
    title = await content.delivery.test_title_for_version(db, session.test_version_id)
    return SessionOut(
        id=session.id,
        test_title=title,
        mode=session.mode,
        status=session.status,
        created_at=session.created_at,
        submitted_at=session.submitted_at,
        audio_purge_after=session.audio_purge_after,
        items=[
            ItemOut(
                part_no=i["part_no"],
                question_no=i["question_no"],
                text=i["text"],
                cue_card=_card(i["cue_card"]),
                prep_seconds=i["prep_seconds"],
                answer_seconds=i["answer_seconds"],
                recording_id=rec.id if rec else None,
                recording_status=rec.status if rec else None,
                duration_ms=rec.duration_ms if rec else None,
                transcript=rec.transcript if rec else None,
            )
            for i in items
            for rec in [by_item.get((i["part_no"], i["question_no"]))]
        ],
        evaluation=evaluation_out(evaluation, names, evaluation.status in RETRYABLE)
        if evaluation
        else None,
        model_answers=[
            ModelAnswerOut(band=a["band"], body=a["body"], author_note=a["author_note"])
            for a in await service.model_answers(db, session)
        ],
    )


async def _summary(db: AsyncSession, s: SpeakingSession) -> SessionSummaryOut:
    e = await service.latest_evaluation(db, s.id)
    return SessionSummaryOut(
        id=s.id,
        test_id=await content.delivery.test_id_for_version(db, s.test_version_id),
        mode=s.mode,
        status=s.status,
        created_at=s.created_at,
        submitted_at=s.submitted_at,
        evaluation_status=e.status if e else None,
        band_overall=float(e.band_overall) if e and e.band_overall is not None else None,
    )


# ------------------------------------------------------------------------------ routes
@router.get("/tests", response_model=list[SpeakingTestOut])
async def list_tests(
    db: Db,
    _: User,
    search: Annotated[str | None, Query(max_length=100)] = None,
    difficulty: content.Difficulty | None = None,
) -> list[SpeakingTestOut]:
    async with db.begin():
        rows = await service.published_tests(
            db, search=search, difficulty=difficulty.value if difficulty else None
        )
    return [_test(t) for t in rows]


@router.get("/tests/{test_id}", response_model=SpeakingTestDetailOut, responses=_problems(404))
async def get_test(test_id: uuid.UUID, db: Db, _: User) -> SpeakingTestDetailOut:
    async with db.begin():
        test, view = await service.published_test(db, test_id)
    return SpeakingTestDetailOut(
        test=_test(test),
        parts=[
            PartOut(
                part_no=p["part_no"],
                topic=p["topic"],
                cue_card=_card(p["cue_card"]),
                questions=p["questions"],
                prep_seconds=p["prep_seconds"],
                answer_seconds=p["answer_seconds"],
            )
            for p in view["parts"]
        ],
        consent_version=identity.VOICE_CONSENT_VERSION,
    )


@router.post(
    "/sessions",
    response_model=SessionOut,
    status_code=status.HTTP_201_CREATED,
    responses=_problems(404),
)
async def start_session(body: StartSessionIn, db: Db, user: User) -> SessionOut:
    async with db.begin():
        session = await service.create_session(db, user.id, body.test_id, body.mode)
        return await _session(db, user.id, session.id)


@router.get("/sessions", response_model=list[SessionSummaryOut])
async def sessions(db: Db, user: User) -> list[SessionSummaryOut]:
    async with db.begin():
        return [await _summary(db, s) for s in await service.history(db, user.id)]


@router.get("/sessions/{session_id}", response_model=SessionOut, responses=_problems(404))
async def get_session(session_id: uuid.UUID, db: Db, user: User) -> SessionOut:
    async with db.begin():
        return await _session(db, user.id, session_id)


@router.post(
    "/sessions/{session_id}/recordings",
    response_model=RecordingTicketOut,
    status_code=status.HTTP_201_CREATED,
    responses=_problems(404, 409, 422, 503),
)
async def start_recording(
    session_id: uuid.UUID, body: RecordingIn, request: Request, db: Db, user: User
) -> RecordingTicketOut:
    store = service.storage(request.app.state.settings)
    async with db.begin():
        recording, url = await service.start_recording(
            db,
            store,
            user.id,
            session_id,
            part_no=body.part_no,
            question_no=body.question_no,
            mime_type=body.mime_type,
            size_bytes=body.size_bytes,
            sha256=body.sha256,
            duration_ms=body.duration_ms,
        )
    return RecordingTicketOut(
        recording_id=recording.id,
        upload_url=url,
        headers={"Content-Type": recording.mime_type},
        expires_in_seconds=PRESIGN_TTL_SECONDS,
    )


@router.post(
    "/sessions/{session_id}/recordings/{recording_id}/complete",
    response_model=RecordingOut,
    responses=_problems(404, 409, 422, 503),
)
async def complete_recording(
    session_id: uuid.UUID, recording_id: uuid.UUID, request: Request, db: Db, user: User
) -> RecordingOut:
    store = service.storage(request.app.state.settings)
    async with db.begin():
        recording, reason = await service.complete_recording(
            db, store, user.id, session_id, recording_id
        )
        out = RecordingOut(id=recording.id, status=recording.status)
    if reason is not None:  # the failed state is committed above
        raise RecordingRejectedError(reason)
    return out


@router.get(
    "/sessions/{session_id}/recordings/{recording_id}/url",
    response_model=AudioUrlOut,
    responses=_problems(404, 503),
)
async def recording_url(
    session_id: uuid.UUID, recording_id: uuid.UUID, request: Request, db: Db, user: User
) -> AudioUrlOut:
    store = service.storage(request.app.state.settings)
    async with db.begin():
        key, mime = await service.playback_key(db, user.id, session_id, recording_id)
    return AudioUrlOut(
        url=await store.presign_get(key, mime), expires_in_seconds=PRESIGN_TTL_SECONDS
    )


@router.post(
    "/sessions/{session_id}/submit", response_model=SessionOut, responses=_problems(404, 409)
)
async def submit(session_id: uuid.UUID, db: Db, user: User, key: IdempotencyKey) -> SessionOut:
    async with db.begin():
        await service.submit(db, user.id, session_id, key=key)
        return await _session(db, user.id, session_id)


@router.post(
    "/sessions/{session_id}/evaluations",
    response_model=SessionOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_problems(404, 409),
)
async def retry(session_id: uuid.UUID, db: Db, user: User, key: IdempotencyKey) -> SessionOut:
    async with db.begin():
        await service.retry(db, user.id, session_id, key=key)
        return await _session(db, user.id, session_id)
