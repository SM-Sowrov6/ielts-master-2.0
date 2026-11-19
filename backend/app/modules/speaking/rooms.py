"""AI Speaking Room: examiner profiles, admin examiner configurations, room lifecycle, transcript.

A room is a `speaking_sessions` row with `kind = 'room'`. At creation it freezes the examiner
profile, the published configuration and an ordered step plan built from the test version's
existing parts (Part 1 questions -> Part 2 cue card -> Part 3 discussion). Lifecycle:
`created` (waiting room) -> `live` -> `completed`.

Conduct modes:
- `guided` (no voice provider): the server emits examiner lines strictly from the frozen plan,
  one question at a time; each candidate step needs a verified recording before the room moves
  on. Follow-up questions are generated only by a live examiner, so none are invented here.
- `live` (voice provider registered, see `voice.py`): the provider conducts the test and posts
  transcript events (`ingest_events`).

Completion queues the existing Speaking evaluation job; without providers it ends `unavailable`.
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.modules.audit import api as audit
from app.modules.content import api as content
from app.modules.identity import api as identity
from app.modules.speaking import voice
from app.modules.speaking.models import (
    ExaminerConfig,
    ExaminerProfile,
    RecordingStatus,
    SessionKind,
    SessionStatus,
    SpeakingRecording,
    SpeakingSession,
    SpeakingTurn,
)
from app.modules.speaking.service import AUDIO_RETENTION_DAYS, _queue
from app.shared.ids import new_id

_STRICT = ConfigDict(extra="forbid")
Criterion = Literal["FC", "LR", "GRA", "PR"]
ALL_CRITERIA: tuple[Criterion, ...] = ("FC", "LR", "GRA", "PR")
Text = Field(default="", max_length=3000)


class RoomError(DomainError):
    status_code = 409
    code = "speaking_room_state"
    title = "This action is not possible in the room's current state"


class RoomNotFoundError(DomainError):
    status_code = 404
    code = "speaking_room_not_found"
    title = "Speaking room not found"


class ConfigInvalidError(DomainError):
    status_code = 422
    code = "examiner_config_invalid"
    title = "The examiner configuration is not valid"


# ------------------------------------------------------------------------------ configuration
class Instructions(BaseModel):
    """Structured examiner instructions. Defaults are the platform's own wording."""

    model_config = _STRICT
    role: str = Field(
        default=(
            "You are a professional, friendly IELTS Speaking examiner conducting a practice test."
        ),
        max_length=3000,
    )
    introduction: str = Field(
        default=(
            "Hello, my name is {examiner} and I'll be your examiner today. I'll ask you some "
            "questions about yourself, then give you a topic to talk about, and finally we'll "
            "discuss some broader questions. Let's begin."
        ),
        max_length=3000,
    )
    tone: str = Field(default="Calm, neutral and encouraging; never judgemental.", max_length=3000)
    question_delivery: str = Field(
        default="Ask one question at a time and wait for the candidate to finish.",
        max_length=3000,
    )
    follow_up_rules: str = Field(
        default="Ask a short follow-up only when the answer is brief or invites development.",
        max_length=3000,
    )
    irrelevant_answers: str = Field(
        default="Politely steer the candidate back to the question once, then move on.",
        max_length=3000,
    )
    silence: str = Field(
        default="After a long silence, rephrase the question once; if silence continues, move on.",
        max_length=3000,
    )
    to_part2: str = Field(
        default=(
            "Thank you. Now I'm going to give you a topic, and I'd like you to talk about it for "
            "one to two minutes. You have one minute to think about what you'd like to say."
        ),
        max_length=3000,
    )
    to_part3: str = Field(
        default=(
            "Thank you. We've been talking about this topic; now I'd like to discuss some more "
            "general questions related to it."
        ),
        max_length=3000,
    )
    completion: str = Field(
        default="Thank you, that is the end of the speaking test. Well done.", max_length=3000
    )
    confidentiality: str = Field(
        default=(
            "Never reveal model answers, scores, criteria or feedback during the test, and never "
            "answer your own questions."
        ),
        max_length=3000,
    )


class Timing(BaseModel):
    model_config = _STRICT
    part1_answer_seconds: int = Field(default=45, ge=15, le=180)
    part2_prep_seconds: int = Field(default=60, ge=0, le=120)
    part2_speak_seconds: int = Field(default=120, ge=30, le=240)
    part3_answer_seconds: int = Field(default=75, ge=15, le=240)
    max_total_minutes: int = Field(default=15, ge=5, le=30)


class FollowUps(BaseModel):
    model_config = _STRICT
    enabled: bool = True
    max_per_question: int = Field(default=1, ge=0, le=3)
    use_candidate_answers: bool = True  # Part 3 follow-ups build on what the candidate said


def _all_criteria() -> list[Criterion]:
    return list(ALL_CRITERIA)


class ExaminerConfigBody(BaseModel):
    model_config = _STRICT
    title: str = Field(min_length=1, max_length=200)
    part1_questions: list[int] = Field(default_factory=list, max_length=20)
    part2_rounding: list[int] = Field(default_factory=list, max_length=5)
    part3_questions: list[int] = Field(default_factory=list, max_length=20)
    timing: Timing = Field(default_factory=Timing)
    follow_ups: FollowUps = Field(default_factory=FollowUps)
    instructions: Instructions = Field(default_factory=Instructions)
    difficulty: Literal["supportive", "standard", "challenging"] = "standard"
    criteria: list[Criterion] = Field(default_factory=_all_criteria, min_length=1)


class SaveConfigIn(BaseModel):
    model_config = _STRICT
    revision: datetime
    body: ExaminerConfigBody


CONVERSATION_RULES = [
    "Ask one question at a time.",
    "Wait for the candidate's response before continuing.",
    "Do not answer your own questions.",
    "Ask follow-up questions only as configured.",
    "Do not reveal expected answers or evaluation feedback during the test.",
    "Follow Part 1, Part 2 and Part 3 in order.",
    "Maintain a natural examiner personality.",
    "Avoid repeating questions unnecessarily.",
    "Keep the test within the configured time.",
    "End the session professionally.",
]


async def _speaking_view(db: AsyncSession, version_id: uuid.UUID) -> dict[str, Any]:
    try:
        return await content.productive.speaking_student_view(db, version_id)
    except content.ContentNotFoundError as exc:
        raise ConfigInvalidError("The Speaking test version is not published.") from exc


def _part(view: dict[str, Any], no: int) -> dict[str, Any]:
    return next((p for p in view["parts"] if p["part_no"] == no), {"questions": [], "topic": ""})


def config_issues(body: ExaminerConfigBody, view: dict[str, Any]) -> list[str]:
    issues = []
    for no, picked in (
        (1, body.part1_questions),
        (2, body.part2_rounding),
        (3, body.part3_questions),
    ):
        count = len(_part(view, no)["questions"])
        if any(i < 0 or i >= count for i in picked) or len(set(picked)) != len(picked):
            issues.append(f"Part {no}: each selected question must exist and appear once.")
    if not body.part1_questions:
        issues.append("Part 1 needs at least one question.")
    if not (_part(view, 2).get("cue_card") or {}).get("prompt"):
        issues.append("The Speaking test has no Part 2 cue card.")
    if not body.part3_questions:
        issues.append("Part 3 needs at least one question.")
    return issues


def build_plan(
    body: ExaminerConfigBody, view: dict[str, Any], examiner_name: str
) -> list[dict[str, Any]]:
    """Ordered examiner/candidate steps (examiner text only from configuration and content)."""
    t, ins = body.timing, body.instructions
    steps: list[dict[str, Any]] = []

    def add(role: str, part: int, kind: str, text: str, **extra: Any) -> None:
        steps.append(
            {"step": len(steps), "role": role, "part_no": part, "kind": kind, "text": text, **extra}
        )

    def ask(part: int, question_no: int, text: str, seconds: int) -> None:
        add("examiner", part, "question", text)
        add(
            "candidate",
            part,
            "answer",
            text,
            question_no=question_no,
            prep_seconds=0,
            answer_seconds=seconds,
        )

    add("examiner", 1, "intro", ins.introduction.replace("{examiner}", examiner_name))
    p1 = _part(view, 1)["questions"]
    for n, i in enumerate(body.part1_questions, start=1):
        ask(1, n, p1[i], t.part1_answer_seconds)
    part2 = _part(view, 2)
    card = part2.get("cue_card") or {}
    add("examiner", 2, "transition", ins.to_part2)
    add("examiner", 2, "cue_card", str(card.get("prompt", "")), cue_card=card)
    add(
        "candidate",
        2,
        "answer",
        str(card.get("prompt", "")),
        question_no=1,
        prep_seconds=t.part2_prep_seconds,
        answer_seconds=t.part2_speak_seconds,
        cue_card=card,
    )
    for n, i in enumerate(body.part2_rounding, start=2):
        ask(2, n, part2["questions"][i], 30)
    add("examiner", 3, "transition", ins.to_part3)
    p3 = _part(view, 3)["questions"]
    for n, i in enumerate(body.part3_questions, start=1):
        ask(3, n, p3[i], t.part3_answer_seconds)
    add("examiner", 3, "closing", ins.completion)
    return steps


def default_body(view: dict[str, Any], title: str) -> ExaminerConfigBody:
    return ExaminerConfigBody(
        title=title,
        part1_questions=list(range(len(_part(view, 1)["questions"]))),
        part2_rounding=list(range(len(_part(view, 2)["questions"]))),
        part3_questions=list(range(len(_part(view, 3)["questions"]))),
    )


# ------------------------------------------------------------------------------ admin
async def list_profiles(db: AsyncSession, *, active_only: bool = False) -> list[ExaminerProfile]:
    query = select(ExaminerProfile).order_by(ExaminerProfile.sort_order, ExaminerProfile.name)
    if active_only:
        query = query.where(ExaminerProfile.is_active)
    return list(await db.scalars(query))


class ProfileIn(BaseModel):
    model_config = _STRICT
    name: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    personality: str = Field(min_length=1, max_length=1000)
    speaking_style: str = Field(min_length=1, max_length=1000)
    accent: str | None = Field(default=None, max_length=80)
    difficulty: Literal["supportive", "standard", "challenging"]
    avatar_tone: Literal["primary", "success", "warning", "info"] = "primary"
    voice: dict[str, str] = Field(default_factory=dict, max_length=10)  # provider-independent
    is_active: bool = True


async def update_profile(
    db: AsyncSession, profile_id: uuid.UUID, data: ProfileIn, *, actor_id: uuid.UUID
) -> ExaminerProfile:
    profile = await db.get(ExaminerProfile, profile_id)
    if profile is None:
        raise RoomNotFoundError("Examiner profile not found.")
    for key, value in data.model_dump().items():
        setattr(profile, key, value)
    await db.flush()
    await db.refresh(profile)
    await audit.record(
        db,
        actor_id=actor_id,
        action="speaking.examiner.update",
        entity_type="examiner_profile",
        entity_id=profile.id,
        changes={},
    )
    return profile


async def list_configs(db: AsyncSession) -> list[ExaminerConfig]:
    return list(await db.scalars(select(ExaminerConfig).order_by(ExaminerConfig.updated_at.desc())))


async def get_config(db: AsyncSession, config_id: uuid.UUID) -> ExaminerConfig:
    config = await db.get(ExaminerConfig, config_id)
    if config is None:
        raise RoomNotFoundError("Examiner configuration not found.")
    return config


async def create_config(
    db: AsyncSession, test_id: uuid.UUID, *, actor_id: uuid.UUID
) -> ExaminerConfig:
    try:
        test = await content.delivery.published_listening_test(db, test_id, "speaking")
    except content.ContentNotFoundError as exc:
        raise ConfigInvalidError("Choose a published Speaking test.") from exc
    view = await _speaking_view(db, test.version_id)
    body = default_body(view, f"{test.title} — AI examiner")
    config = ExaminerConfig(
        test_id=test.test_id,
        test_version_id=test.version_id,
        title=body.title,
        config=body.model_dump(mode="json"),
        created_by=actor_id,
    )
    db.add(config)
    await db.flush()
    await db.refresh(config)
    await audit.record(
        db,
        actor_id=actor_id,
        action="speaking.examiner_config.create",
        entity_type="examiner_config",
        entity_id=config.id,
        changes={"test_id": str(test_id)},
    )
    return config


async def save_config(
    db: AsyncSession, config_id: uuid.UUID, data: SaveConfigIn, *, actor_id: uuid.UUID
) -> tuple[ExaminerConfig, list[str]]:
    config = await get_config(db, config_id)
    if config.status == "published":
        raise RoomError("Unpublish the configuration before editing it.")
    if config.updated_at != data.revision:
        raise RoomError("The configuration was changed elsewhere. Reload and try again.")
    view = await _speaking_view(db, config.test_version_id)
    issues = [i for i in config_issues(data.body, view) if "each selected question" in i]
    if issues:
        raise ConfigInvalidError("; ".join(issues))
    config.title = data.body.title
    config.config = data.body.model_dump(mode="json")
    config.updated_at = func.now()
    await db.flush()
    await db.refresh(config)
    await audit.record(
        db,
        actor_id=actor_id,
        action="speaking.examiner_config.save",
        entity_type="examiner_config",
        entity_id=config.id,
        changes={},
    )
    return config, config_issues(data.body, view)


async def set_published(
    db: AsyncSession, config_id: uuid.UUID, publish: bool, *, actor_id: uuid.UUID
) -> ExaminerConfig:
    config = await get_config(db, config_id)
    if publish:
        view = await _speaking_view(db, config.test_version_id)
        issues = config_issues(ExaminerConfigBody.model_validate(config.config), view)
        if issues:
            raise ConfigInvalidError("; ".join(issues))
        config.status, config.published_at, config.published_by = (
            "published",
            datetime.now(UTC),
            actor_id,
        )
    else:
        if config.status != "published":
            raise RoomError("Only a published configuration can be unpublished.")
        config.status = "unpublished"
    await db.flush()
    await db.refresh(config)
    await audit.record(
        db,
        actor_id=actor_id,
        action="speaking.examiner_config." + ("publish" if publish else "unpublish"),
        entity_type="examiner_config",
        entity_id=config.id,
        changes={},
    )
    return config


async def delete_config(db: AsyncSession, config_id: uuid.UUID, *, actor_id: uuid.UUID) -> None:
    config = await get_config(db, config_id)
    if config.status == "published":
        raise RoomError("Unpublish the configuration before deleting it.")
    used = await db.scalar(
        select(SpeakingSession.id).where(SpeakingSession.examiner_config_id == config.id).limit(1)
    )
    if used is not None:
        raise RoomError("Candidates have used this configuration; unpublish it instead.")
    await db.delete(config)
    await audit.record(
        db,
        actor_id=actor_id,
        action="speaking.examiner_config.delete",
        entity_type="examiner_config",
        entity_id=config_id,
        changes={},
    )


async def preview(
    db: AsyncSession, config: ExaminerConfig, examiner_name: str = "your examiner"
) -> dict[str, Any]:
    view = await _speaking_view(db, config.test_version_id)
    body = ExaminerConfigBody.model_validate(config.config)
    issues = config_issues(body, view)
    return {
        "issues": issues,
        "rules": CONVERSATION_RULES,
        "plan": []
        if any("each selected" in i for i in issues)
        else build_plan(body, view, examiner_name),
        "available": {
            "part1": _part(view, 1)["questions"],
            "part2_rounding": _part(view, 2)["questions"],
            "part3": _part(view, 3)["questions"],
            "cue_card": _part(view, 2).get("cue_card"),
            "topics": {p["part_no"]: p["topic"] for p in view["parts"]},
        },
    }


# ------------------------------------------------------------------------------ candidate
async def room_tests(db: AsyncSession) -> list[tuple[ExaminerConfig, str]]:
    configs = await db.scalars(
        select(ExaminerConfig)
        .where(ExaminerConfig.status == "published")
        .order_by(ExaminerConfig.published_at.desc())
    )
    return [
        (c, await content.delivery.test_title_for_version(db, c.test_version_id)) for c in configs
    ]


def _profile_snapshot(p: ExaminerProfile) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "code": p.code,
        "name": p.name,
        "title": p.title,
        "personality": p.personality,
        "speaking_style": p.speaking_style,
        "accent": p.accent,
        "difficulty": p.difficulty,
        "avatar_tone": p.avatar_tone,
        "voice": p.voice,
    }


async def create_room(
    db: AsyncSession, user_id: uuid.UUID, *, examiner_id: uuid.UUID, config_id: uuid.UUID
) -> SpeakingSession:
    examiner = await db.get(ExaminerProfile, examiner_id)
    config = await db.get(ExaminerConfig, config_id)
    if examiner is None or not examiner.is_active or config is None or config.status != "published":
        raise RoomNotFoundError("This examiner or test is not available.")
    view = await _speaking_view(db, config.test_version_id)
    body = ExaminerConfigBody.model_validate(config.config)
    if config_issues(body, view):
        raise ConfigInvalidError("This test's examiner configuration is incomplete.")
    processing, recording = await identity.grant_voice_consents(db, user_id)
    title = await content.delivery.test_title_for_version(db, config.test_version_id)
    session = SpeakingSession(
        user_id=user_id,
        test_version_id=config.test_version_id,
        mode="full",
        status=SessionStatus.CREATED.value,
        kind=SessionKind.ROOM.value,
        room_code=f"room-{secrets.token_urlsafe(12)}",
        examiner_id=examiner.id,
        examiner_config_id=config.id,
        processing_consent_id=processing,
        recording_consent_id=recording,
        config_snapshot={
            "test_title": title,
            "examiner": _profile_snapshot(examiner),
            "instructions": body.instructions.model_dump(),
            "rules": CONVERSATION_RULES,
            "timing": body.timing.model_dump(),
            "follow_ups": body.follow_ups.model_dump(),
            "difficulty": body.difficulty,
            "criteria": list(body.criteria),
            "plan": build_plan(body, view, examiner.name),
        },
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return session


async def owned_room(
    db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID, *, lock: bool = False
) -> SpeakingSession:
    query = select(SpeakingSession).where(
        SpeakingSession.id == session_id,
        SpeakingSession.user_id == user_id,
        SpeakingSession.kind == SessionKind.ROOM.value,
    )
    if lock:
        query = query.with_for_update()
    room = await db.scalar(query)
    if room is None:
        raise RoomNotFoundError()
    return room


def plan(room: SpeakingSession) -> list[dict[str, Any]]:
    return list((room.config_snapshot or {}).get("plan", []))


def room_items(room: SpeakingSession) -> list[dict[str, Any]]:
    """The candidate answer steps, in the shape the recording pipeline expects."""
    return [
        {
            "part_no": s["part_no"],
            "question_no": s["question_no"],
            "text": s["text"],
            "cue_card": s.get("cue_card"),
            "prep_seconds": s.get("prep_seconds", 0),
            "answer_seconds": s.get("answer_seconds", 60),
        }
        for s in plan(room)
        if s["role"] == "candidate"
    ]


async def _next_seq(db: AsyncSession, room: SpeakingSession) -> int:
    top = await db.scalar(
        select(func.max(SpeakingTurn.seq)).where(SpeakingTurn.session_id == room.id)
    )
    return (top or 0) + 1


def _offset_ms(room: SpeakingSession) -> int | None:
    return (
        int((datetime.now(UTC) - room.started_at).total_seconds() * 1000)
        if room.started_at
        else None
    )


async def _emit_examiner(db: AsyncSession, room: SpeakingSession) -> None:
    """Guided mode: write examiner steps from the frozen plan up to the next candidate step."""
    steps = plan(room)
    seq = await _next_seq(db, room)
    while room.current_step < len(steps) and steps[room.current_step]["role"] == "examiner":
        s = steps[room.current_step]
        db.add(
            SpeakingTurn(
                session_id=room.id,
                seq=seq,
                speaker="examiner",
                part_no=s["part_no"],
                step=s["step"],
                text=s["text"],
                offset_ms=_offset_ms(room),
                meta={"kind": s["kind"], "source": "configuration"},
            )
        )
        seq += 1
        room.current_step += 1
    if room.current_step >= len(steps):
        await _complete(db, room, "finished")


async def _complete(db: AsyncSession, room: SpeakingSession, reason: str) -> None:
    now = datetime.now(UTC)
    room.status = SessionStatus.COMPLETED.value
    room.ended_at = now
    room.completion_reason = reason
    room.duration_seconds = int((now - room.started_at).total_seconds()) if room.started_at else 0
    room.submitted_at = now
    room.audio_purge_after = now + timedelta(days=AUDIO_RETENTION_DAYS)
    has_audio = await db.scalar(
        select(SpeakingRecording.id)
        .where(
            SpeakingRecording.session_id == room.id,
            SpeakingRecording.status == RecordingStatus.READY.value,
        )
        .limit(1)
    )
    spoken = await db.scalar(
        select(SpeakingTurn.id)
        .where(
            SpeakingTurn.session_id == room.id,
            SpeakingTurn.speaker == "candidate",
            SpeakingTurn.text != "",
        )
        .limit(1)
    )
    # Evaluation needs at least one verified recording (guided) or transcribed answer (live).
    if has_audio is not None or spoken is not None:
        room.submit_key = new_id()
        _queue(db, room.id, room.submit_key, room.user_id)


async def enter(
    db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID
) -> tuple[SpeakingSession, voice.VoiceConnection | None]:
    room = await owned_room(db, user_id, session_id, lock=True)
    if room.status != SessionStatus.CREATED.value:
        return room, None  # entering twice (reload) keeps the room as it is
    room.status = SessionStatus.LIVE.value
    room.started_at = datetime.now(UTC)
    adapter = voice.provider()
    connection = None
    if adapter is not None:
        snap = room.config_snapshot or {}
        connection = await adapter.create_session(
            voice.RoomContext(
                str(room.id),
                str(room.room_code),
                str(user_id),
                snap.get("examiner", {}),
                {
                    **snap.get("instructions", {}),
                    "rules": snap.get("rules", []),
                    "timing": snap.get("timing", {}),
                    "follow_ups": snap.get("follow_ups", {}),
                },
                plan(room),
            )
        )
        room.conduct_mode = "live"
    else:
        room.conduct_mode = "guided"
        await _emit_examiner(db, room)
    await db.flush()
    await db.refresh(room)
    return room, connection


async def advance(
    db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID, step: int
) -> SpeakingSession:
    """Guided mode: the candidate finished answering `step` (its recording is verified)."""
    room = await owned_room(db, user_id, session_id, lock=True)
    if step < room.current_step and room.conduct_mode == "guided":
        return room  # retried request (also after the room completed)
    if room.status != SessionStatus.LIVE.value or room.conduct_mode != "guided":
        raise RoomError()
    steps = plan(room)
    if step != room.current_step or step >= len(steps) or steps[step]["role"] != "candidate":
        raise RoomError("That is not the current answer.")
    s = steps[step]
    recording = await db.scalar(
        select(SpeakingRecording).where(
            SpeakingRecording.session_id == room.id,
            SpeakingRecording.part_no == s["part_no"],
            SpeakingRecording.question_no == s["question_no"],
            SpeakingRecording.status == RecordingStatus.READY.value,
        )
    )
    if recording is None:
        raise RoomError("Record your answer before continuing.")
    db.add(
        SpeakingTurn(
            session_id=room.id,
            seq=await _next_seq(db, room),
            speaker="candidate",
            part_no=s["part_no"],
            step=step,
            text="",
            offset_ms=_offset_ms(room),
            meta={
                "recording_id": str(recording.id),
                "duration_ms": recording.duration_ms,
                "transcript": "pending",
            },
        )
    )
    await db.flush()  # the next examiner line numbers itself after this one
    room.current_step += 1
    await _emit_examiner(db, room)
    await db.flush()
    await db.refresh(room)
    return room


async def end(db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID) -> SpeakingSession:
    room = await owned_room(db, user_id, session_id, lock=True)
    if room.status == SessionStatus.COMPLETED.value:
        return room
    adapter = voice.provider()
    if adapter is not None and room.conduct_mode == "live":
        await adapter.end_session(str(room.room_code))
    await _complete(db, room, "ended_by_candidate")
    await db.flush()
    await db.refresh(room)
    return room


async def voice_token(
    db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID
) -> voice.VoiceConnection:
    """A fresh participant token for a live room (e.g. after a page reload)."""
    room = await owned_room(db, user_id, session_id)
    adapter = voice.provider()
    if (
        room.status != SessionStatus.LIVE.value
        or room.conduct_mode != "live"
        or adapter is None
        or not hasattr(adapter, "candidate_token")
    ):
        raise RoomError("This room has no live voice connection.")
    connection: voice.VoiceConnection = adapter.candidate_token(str(room.room_code), str(user_id))
    return connection


async def turns(db: AsyncSession, room: SpeakingSession) -> list[SpeakingTurn]:
    return list(
        await db.scalars(
            select(SpeakingTurn)
            .where(SpeakingTurn.session_id == room.id)
            .order_by(SpeakingTurn.seq)
        )
    )


class TranscriptEvent(BaseModel):
    """One event from the live voice provider (TranscriptEventHandler input)."""

    model_config = _STRICT
    seq: int = Field(ge=1)
    type: Literal["transcript", "part", "completed"]
    speaker: Literal["examiner", "candidate", "system"] = "system"
    text: str = Field(default="", max_length=5000)
    part_no: Literal[1, 2, 3] | None = None
    offset_ms: int | None = Field(default=None, ge=0)
    meta: dict[str, Any] = Field(default_factory=dict)


async def ingest_events(
    db: AsyncSession, session_id: uuid.UUID, events: list[TranscriptEvent]
) -> int:
    """Idempotent on (session, seq). Only live rooms accept provider events."""
    room = await db.scalar(
        select(SpeakingSession)
        .where(SpeakingSession.id == session_id, SpeakingSession.kind == SessionKind.ROOM.value)
        .with_for_update()
    )
    if room is None:
        raise RoomNotFoundError()
    if room.conduct_mode != "live" or room.status != SessionStatus.LIVE.value:
        raise RoomError("This room is not receiving live events.")
    stored = 0
    for e in events:
        if e.type == "completed":
            await _complete(db, room, "finished")
            continue
        result = await db.execute(
            insert(SpeakingTurn)
            .values(
                id=new_id(),
                session_id=room.id,
                seq=e.seq,
                speaker=e.speaker if e.type == "transcript" else "system",
                part_no=e.part_no,
                step=None,
                text=e.text,
                offset_ms=e.offset_ms,
                meta={**e.meta, "type": e.type, "source": "voice_provider"},
            )
            .on_conflict_do_nothing(index_elements=["session_id", "seq"])
        )
        stored += result.rowcount or 0  # type: ignore[attr-defined]
    await db.flush()
    return stored


async def history(db: AsyncSession, user_id: uuid.UUID) -> list[SpeakingSession]:
    return list(
        await db.scalars(
            select(SpeakingSession)
            .where(
                SpeakingSession.user_id == user_id, SpeakingSession.kind == SessionKind.ROOM.value
            )
            .order_by(SpeakingSession.created_at.desc())
            .limit(50)
        )
    )
