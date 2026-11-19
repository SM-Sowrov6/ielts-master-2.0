"""Candidate AI Speaking Room API under /api/v1/speaking (owner-only), plus the internal transcript
event endpoint for the future voice engine (disabled unless `speaking_events_token` is set)."""

import hmac
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.errors import PROBLEM_MEDIA_TYPE
from app.modules.identity import api as identity
from app.modules.speaking import rooms, service, voice
from app.modules.speaking.models import ExaminerProfile, SpeakingRecording, SpeakingSession
from app.shared.evaluation import RETRYABLE
from app.shared.evaluation_schemas import EvaluationOut, ModelAnswerOut, evaluation_out

Db = Annotated[AsyncSession, Depends(get_db_session)]
User = Annotated[identity.CurrentUser, Depends(identity.current_user)]
_STRICT = ConfigDict(extra="forbid")


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _problems(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {c: {"description": "Problem", "content": {PROBLEM_MEDIA_TYPE: {}}} for c in codes}


router = APIRouter(
    prefix="/api/v1/speaking",
    tags=["speaking-room"],
    dependencies=[Depends(_no_store)],
    responses=_problems(401),
)
internal = APIRouter(prefix="/api/v1/internal/speaking", tags=["internal"], include_in_schema=False)


class ExaminerOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    title: str
    personality: str
    speaking_style: str
    accent: str | None
    difficulty: Literal["supportive", "standard", "challenging"]
    avatar_tone: str
    voice_configured: bool


class RoomTestOut(BaseModel):
    config_id: uuid.UUID
    test_id: uuid.UUID
    title: str
    test_title: str
    difficulty: str
    part1_questions: int
    part3_questions: int
    max_total_minutes: int


class CreateRoomIn(BaseModel):
    model_config = _STRICT
    examiner_id: uuid.UUID
    config_id: uuid.UUID
    voice_processing_consent: Literal[True]
    audio_recording_consent: Literal[True]


class RoomCueCardOut(BaseModel):
    prompt: str
    points: list[str] = []
    closing: str | None = None


class CurrentStepOut(BaseModel):
    step: int
    part_no: int
    question_no: int
    text: str
    cue_card: RoomCueCardOut | None
    prep_seconds: int
    answer_seconds: int
    recording_id: uuid.UUID | None
    recording_status: str | None


class TurnOut(BaseModel):
    seq: int
    speaker: Literal["examiner", "candidate", "system"]
    part_no: int | None
    kind: str | None
    text: str
    offset_ms: int | None
    created_at: datetime
    recording_id: uuid.UUID | None
    duration_ms: int | None
    transcript_status: Literal["pending", "available"] | None


class VoiceStatusOut(BaseModel):
    mode: Literal["guided", "live"] | None
    live_available: bool
    message: str


class VoiceConnectionOut(BaseModel):
    provider: str
    url: str
    token: str
    expires_at: datetime


class LivePhaseOut(BaseModel):
    """Live mode: what the examiner agent last signalled (e.g. Part 2 preparation)."""

    phase: str
    part_no: int | None
    seconds: int | None
    since: datetime


class RoomOut(BaseModel):
    id: uuid.UUID
    room_code: str
    status: Literal["created", "live", "completed"]
    test_title: str
    examiner: ExaminerOut
    timing: dict[str, int]
    criteria: list[str]
    current_part: int | None
    current_step: int
    total_steps: int
    answers_total: int
    answers_done: int
    current: CurrentStepOut | None
    cue_card: RoomCueCardOut | None
    live_phase: LivePhaseOut | None
    transcript: list[TurnOut]
    voice: VoiceStatusOut
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    completion_reason: str | None
    evaluation: EvaluationOut | None
    model_answers: list[ModelAnswerOut]


class EnterOut(BaseModel):
    room: RoomOut
    connection: VoiceConnectionOut | None


class AdvanceIn(BaseModel):
    model_config = _STRICT
    step: int = Field(ge=0, le=500)


class RoomSummaryOut(BaseModel):
    id: uuid.UUID
    test_title: str
    examiner_name: str
    status: str
    created_at: datetime
    duration_seconds: int | None
    evaluation_status: str | None
    band_overall: float | None


class EventsIn(BaseModel):
    model_config = _STRICT
    events: list[rooms.TranscriptEvent] = Field(min_length=1, max_length=200)


def examiner_out(p: ExaminerProfile | dict[str, Any]) -> ExaminerOut:
    d = p if isinstance(p, dict) else rooms._profile_snapshot(p)
    return ExaminerOut(
        id=uuid.UUID(str(d["id"])),
        code=d["code"],
        name=d["name"],
        title=d["title"],
        personality=d["personality"],
        speaking_style=d["speaking_style"],
        accent=d.get("accent"),
        difficulty=d["difficulty"],
        avatar_tone=d.get("avatar_tone", "primary"),
        voice_configured=bool(d.get("voice")) and voice.provider() is not None,
    )


def _voice(room: SpeakingSession) -> VoiceStatusOut:
    live = voice.provider() is not None
    return VoiceStatusOut(
        mode=room.conduct_mode,
        live_available=live,
        message=(
            "Live AI voice examiner connected."
            if room.conduct_mode == "live"
            else "Guided mode: the AI voice examiner is not connected yet. Questions come from "
            "the published test configuration; your spoken answers are recorded and assessed "
            "after the session."
        ),
    )


async def room_out(db: AsyncSession, room: SpeakingSession) -> RoomOut:
    snap = room.config_snapshot or {}
    steps = rooms.plan(room)
    recordings = {
        (r.part_no, r.question_no): r
        for r in await db.scalars(
            select(SpeakingRecording).where(SpeakingRecording.session_id == room.id)
        )
    }
    by_id = {str(r.id): r for r in recordings.values()}
    current = None
    if room.status == "live" and room.current_step < len(steps):
        s = steps[room.current_step]
        if s["role"] == "candidate":
            rec = recordings.get((s["part_no"], s["question_no"]))
            current = CurrentStepOut(
                step=s["step"],
                part_no=s["part_no"],
                question_no=s["question_no"],
                text=s["text"],
                cue_card=(
                    RoomCueCardOut.model_validate(s["cue_card"]) if s.get("cue_card") else None
                ),
                prep_seconds=s.get("prep_seconds", 0),
                answer_seconds=s.get("answer_seconds", 60),
                recording_id=rec.id if rec else None,
                recording_status=rec.status if rec else None,
            )
    transcript = []
    live_phase = None
    last_part: int | None = None
    for t in await rooms.turns(db, room):
        if t.part_no:
            last_part = t.part_no
        if t.speaker == "system":
            if t.meta.get("type") == "part" and t.meta.get("phase"):
                seconds = t.meta.get("seconds")
                live_phase = LivePhaseOut(
                    phase=str(t.meta["phase"]),
                    part_no=t.part_no,
                    seconds=int(seconds) if isinstance(seconds, int) else None,
                    since=t.created_at,
                )
            continue
        rec = by_id.get(str(t.meta.get("recording_id"))) if t.meta.get("recording_id") else None
        text = t.text or (rec.transcript if rec and rec.transcript else "")
        transcript.append(
            TurnOut(
                seq=t.seq,
                speaker=t.speaker,
                part_no=t.part_no,
                kind=t.meta.get("kind"),
                text=text,
                offset_ms=t.offset_ms,
                created_at=t.created_at,
                recording_id=rec.id if rec else None,
                duration_ms=rec.duration_ms if rec else None,
                transcript_status=("available" if text else "pending") if rec else None,
            )
        )
    candidate_steps = [s for s in steps if s["role"] == "candidate"]
    part = steps[min(room.current_step, len(steps) - 1)]["part_no"] if steps else None
    if room.conduct_mode == "live":
        part = last_part or 1
    card = next((s.get("cue_card") for s in steps if s.get("kind") == "cue_card"), None)
    evaluation = await service.latest_evaluation(db, room.id)
    names = await service.rubric_names(db, evaluation.rubric_version_id if evaluation else None)
    return RoomOut(
        id=room.id,
        room_code=str(room.room_code),
        status=room.status,
        test_title=str(snap.get("test_title", "")),
        examiner=examiner_out(snap["examiner"]),
        timing=snap.get("timing", {}),
        criteria=snap.get("criteria", []),
        current_part=part if room.status == "live" else None,
        current_step=room.current_step,
        total_steps=len(steps),
        answers_total=len(candidate_steps),
        # live rooms may hold follow-up answers too; the count never exceeds the scripted total
        answers_done=min(
            len(candidate_steps), sum(1 for t in transcript if t.speaker == "candidate")
        ),
        current=current,
        cue_card=RoomCueCardOut.model_validate(card) if card else None,
        live_phase=live_phase,
        transcript=transcript,
        voice=_voice(room),
        created_at=room.created_at,
        started_at=room.started_at,
        ended_at=room.ended_at,
        duration_seconds=room.duration_seconds,
        completion_reason=room.completion_reason,
        evaluation=evaluation_out(evaluation, names, evaluation.status in RETRYABLE)
        if evaluation
        else None,
        model_answers=[
            ModelAnswerOut(band=a["band"], body=a["body"], author_note=a["author_note"])
            for a in await service.model_answers(db, room)
        ],
    )


@router.get("/examiners", response_model=list[ExaminerOut])
async def examiners(db: Db, _: User) -> list[ExaminerOut]:
    async with db.begin():
        return [examiner_out(p) for p in await rooms.list_profiles(db, active_only=True)]


@router.get("/room-tests", response_model=list[RoomTestOut])
async def room_tests(db: Db, _: User) -> list[RoomTestOut]:
    async with db.begin():
        rows = await rooms.room_tests(db)
    out = []
    for config, test_title in rows:
        body = rooms.ExaminerConfigBody.model_validate(config.config)
        out.append(
            RoomTestOut(
                config_id=config.id,
                test_id=config.test_id,
                title=config.title,
                test_title=test_title,
                difficulty=body.difficulty,
                part1_questions=len(body.part1_questions),
                part3_questions=len(body.part3_questions),
                max_total_minutes=body.timing.max_total_minutes,
            )
        )
    return out


@router.post(
    "/rooms",
    response_model=RoomOut,
    status_code=status.HTTP_201_CREATED,
    responses=_problems(404, 422),
)
async def create_room(body: CreateRoomIn, db: Db, user: User) -> RoomOut:
    async with db.begin():
        room = await rooms.create_room(
            db, user.id, examiner_id=body.examiner_id, config_id=body.config_id
        )
        return await room_out(db, room)


@router.get("/rooms", response_model=list[RoomSummaryOut])
async def list_rooms(db: Db, user: User) -> list[RoomSummaryOut]:
    async with db.begin():
        out = []
        for r in await rooms.history(db, user.id):
            e = await service.latest_evaluation(db, r.id)
            snap = r.config_snapshot or {}
            out.append(
                RoomSummaryOut(
                    id=r.id,
                    test_title=str(snap.get("test_title", "")),
                    examiner_name=str(snap.get("examiner", {}).get("name", "")),
                    status=r.status,
                    created_at=r.created_at,
                    duration_seconds=r.duration_seconds,
                    evaluation_status=e.status if e else None,
                    band_overall=float(e.band_overall)
                    if e and e.band_overall is not None
                    else None,
                )
            )
        return out


@router.get("/rooms/{room_id}", response_model=RoomOut, responses=_problems(404))
async def get_room(room_id: uuid.UUID, db: Db, user: User) -> RoomOut:
    async with db.begin():
        return await room_out(db, await rooms.owned_room(db, user.id, room_id))


@router.post("/rooms/{room_id}/enter", response_model=EnterOut, responses=_problems(404))
async def enter_room(room_id: uuid.UUID, db: Db, user: User) -> EnterOut:
    async with db.begin():
        room, connection = await rooms.enter(db, user.id, room_id)
        out = await room_out(db, room)
    return EnterOut(
        room=out,
        connection=VoiceConnectionOut(**connection.__dict__) if connection else None,
    )


@router.post(
    "/rooms/{room_id}/voice-token", response_model=VoiceConnectionOut, responses=_problems(404, 409)
)
async def voice_token(room_id: uuid.UUID, db: Db, user: User) -> VoiceConnectionOut:
    """A fresh LiveKit participant token for a live room (after a reload or expiry)."""
    async with db.begin():
        connection = await rooms.voice_token(db, user.id, room_id)
    return VoiceConnectionOut(**connection.__dict__)


@router.post("/rooms/{room_id}/advance", response_model=RoomOut, responses=_problems(404, 409))
async def advance(room_id: uuid.UUID, body: AdvanceIn, db: Db, user: User) -> RoomOut:
    async with db.begin():
        room = await rooms.advance(db, user.id, room_id, body.step)
        return await room_out(db, room)


@router.post("/rooms/{room_id}/end", response_model=RoomOut, responses=_problems(404))
async def end_room(room_id: uuid.UUID, db: Db, user: User) -> RoomOut:
    async with db.begin():
        room = await rooms.end(db, user.id, room_id)
        return await room_out(db, room)


@internal.post("/rooms/{room_id}/events", status_code=status.HTTP_202_ACCEPTED)
async def ingest(
    room_id: uuid.UUID,
    body: EventsIn,
    request: Request,
    db: Db,
    token: Annotated[str | None, Header(alias="X-Internal-Token")] = None,
) -> dict[str, int]:
    """Voice engine -> transcript/lifecycle events. 404 unless a token is configured and matches."""
    expected = request.app.state.settings.speaking_events_token
    if (
        expected is None
        or token is None
        or not hmac.compare_digest(token, expected.get_secret_value())
    ):
        raise rooms.RoomNotFoundError()
    async with db.begin():
        stored = await rooms.ingest_events(db, room_id, body.events)
    return {"stored": stored}
