"""Candidate Speaking practice: consented sessions, browser recordings uploaded straight to private
object storage, verified server-side, and AI evaluation as a background job
(outbox topic `speaking.evaluate`).

- A session requires explicit voice-processing and audio-recording consents (stored rows).
- Each question gets one recording; re-recording replaces it (new object key, old one deleted).
- Completion verifies size, SHA-256 and the audio container signature; failures never count.
- The job transcribes every answer (STT provider), scores FC/LR/GRA from transcripts and PR only
  from an audio pronunciation assessor (ADR-011). Without providers it ends `unavailable`.
- Audio is purged after `AUDIO_RETENTION_DAYS` (column `audio_purge_after`).
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import structlog
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ai
from app.core.config import Settings
from app.core.outbox import HandlerResult, OutboxContext, enqueue
from app.core.storage import ObjectStorage, StorageUnavailableError
from app.modules.content import api as content
from app.modules.identity import api as identity
from app.modules.speaking.errors import (
    EvaluationNotRetryableError,
    RecordingRejectedError,
    RecordingsIncompleteError,
    RecordingStorageUnavailableError,
    SessionLockedError,
    SessionNotFoundError,
    SpeakingTestUnavailableError,
)
from app.modules.speaking.models import (
    RecordingStatus,
    SessionStatus,
    SpeakingEvaluation,
    SpeakingRecording,
    SpeakingSession,
)
from app.shared.evaluation import RETRYABLE, EvaluationStatus
from app.shared.ids import new_id
from ielts_ai.graphs.evaluation import (
    EvaluationOutputError,
    RubricCriterion,
    SpokenAnswer,
    evaluate_speaking,
)
from ielts_ai.guardrails.input import InputRejectedError
from ielts_ai.providers.gemini import GeminiError
from ielts_ai.schemas.evaluation import overall_band

log = structlog.get_logger(__name__)
TOPIC = "speaking.evaluate"
MAX_EVAL_ATTEMPTS = 3
STALE_RUN = timedelta(minutes=15)
MAX_RECORDING_BYTES = 25 * 1024 * 1024
AUDIO_RETENTION_DAYS = 30
BAND_COLUMNS = {"FC": "band_fc", "LR": "band_lr", "GRA": "band_gra", "PR": "band_pr"}
MIME_EXT = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/wav": "wav"}
MODE_PARTS = {"full": (1, 2, 3), "part1": (1,), "part2": (2,), "part3": (3,)}


def _now() -> datetime:
    return datetime.now(UTC)


def base_mime(mime: str) -> str:
    return mime.split(";")[0].strip().lower()


def signature_ok(mime: str, head: bytes) -> bool:
    kind = base_mime(mime)
    if kind == "audio/webm":
        return head.startswith(b"\x1a\x45\xdf\xa3")
    if kind == "audio/ogg":
        return head.startswith(b"OggS")
    if kind == "audio/mp4":
        return head[4:8] == b"ftyp"
    if kind == "audio/wav":
        return head.startswith(b"RIFF") and head[8:12] == b"WAVE"
    return False


def storage(settings: Settings) -> ObjectStorage:
    try:
        return ObjectStorage(settings)
    except StorageUnavailableError as exc:
        raise RecordingStorageUnavailableError() from exc


# ------------------------------------------------------------------------------ catalogue
async def published_tests(
    db: AsyncSession, *, search: str | None, difficulty: str | None
) -> list[Any]:
    return await content.delivery.published_listening_tests(
        db, search=search, difficulty=difficulty, module="speaking"
    )


async def published_test(db: AsyncSession, test_id: uuid.UUID) -> tuple[Any, dict[str, Any]]:
    try:
        test = await content.delivery.published_listening_test(db, test_id, "speaking")
        view = await content.productive.speaking_student_view(db, test.version_id)
    except content.ContentNotFoundError as exc:
        raise SpeakingTestUnavailableError() from exc
    return test, view


def items_for(view: dict[str, Any], mode: str) -> list[dict[str, Any]]:
    """The questions the candidate answers, in order: (part_no, question_no, text)."""
    items: list[dict[str, Any]] = []
    for part in view["parts"]:
        if part["part_no"] not in MODE_PARTS[mode]:
            continue
        if part["part_no"] == 2:
            card = part.get("cue_card") or {}
            items.append(
                {
                    "part_no": 2,
                    "question_no": 1,
                    "text": str(card.get("prompt") or part["topic"]),
                    "cue_card": card,
                    "prep_seconds": part["prep_seconds"],
                    "answer_seconds": part["answer_seconds"],
                }
            )
            continue
        for index, question in enumerate(part["questions"], start=1):
            items.append(
                {
                    "part_no": part["part_no"],
                    "question_no": index,
                    "text": question,
                    "cue_card": None,
                    "prep_seconds": 0,
                    "answer_seconds": part["answer_seconds"],
                }
            )
    return items


# ------------------------------------------------------------------------------ sessions
async def _owned(
    db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID, *, lock: bool = False
) -> SpeakingSession:
    query = select(SpeakingSession).where(
        SpeakingSession.id == session_id, SpeakingSession.user_id == user_id
    )
    if lock:
        query = query.with_for_update()
    found = await db.scalar(query)
    if found is None:
        raise SessionNotFoundError()
    return found


async def create_session(
    db: AsyncSession, user_id: uuid.UUID, test_id: uuid.UUID, mode: str
) -> SpeakingSession:
    test, view = await published_test(db, test_id)
    if not items_for(view, mode):
        raise SpeakingTestUnavailableError("This part has no questions.")
    processing, recording = await identity.grant_voice_consents(db, user_id)
    session = SpeakingSession(
        user_id=user_id,
        test_version_id=test.version_id,
        mode=mode,
        processing_consent_id=processing,
        recording_consent_id=recording,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return session


def _items(session: SpeakingSession, view: dict[str, Any]) -> list[dict[str, Any]]:
    if session.kind == "room":
        from app.modules.speaking.rooms import room_items

        return room_items(session)
    return items_for(view, session.mode)


async def session_detail(
    db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID
) -> tuple[SpeakingSession, list[dict[str, Any]], list[SpeakingRecording], dict[str, Any]]:
    session = await _owned(db, user_id, session_id)
    view = await content.productive.speaking_student_view(db, session.test_version_id)
    recordings = list(
        await db.scalars(
            select(SpeakingRecording)
            .where(SpeakingRecording.session_id == session.id)
            .order_by(SpeakingRecording.part_no, SpeakingRecording.question_no)
        )
    )
    return session, _items(session, view), recordings, view


async def history(db: AsyncSession, user_id: uuid.UUID) -> list[SpeakingSession]:
    return list(
        await db.scalars(
            select(SpeakingSession)
            .where(SpeakingSession.user_id == user_id, SpeakingSession.kind == "recorded")
            .order_by(SpeakingSession.created_at.desc())
            .limit(100)
        )
    )


async def start_recording(
    db: AsyncSession,
    store: ObjectStorage,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    *,
    part_no: int,
    question_no: int,
    mime_type: str,
    size_bytes: int,
    sha256: str,
    duration_ms: int,
) -> tuple[SpeakingRecording, str]:
    session = await _owned(db, user_id, session_id, lock=True)
    if session.status not in (SessionStatus.RECORDING.value, SessionStatus.LIVE.value):
        raise SessionLockedError()
    kind = base_mime(mime_type)
    if kind not in MIME_EXT or size_bytes > MAX_RECORDING_BYTES:
        raise RecordingRejectedError("Unsupported audio format or file too large.")
    view = await content.productive.speaking_student_view(db, session.test_version_id)
    item = next(
        (
            i
            for i in _items(session, view)
            if i["part_no"] == part_no and i["question_no"] == question_no
        ),
        None,
    )
    if item is None:
        raise RecordingRejectedError("No such question in this session.")
    previous = await db.scalar(
        select(SpeakingRecording).where(
            SpeakingRecording.session_id == session.id,
            SpeakingRecording.part_no == part_no,
            SpeakingRecording.question_no == question_no,
        )
    )
    if previous is not None:  # re-record: the old object is removed with its row
        old_key = previous.storage_key
        await db.delete(previous)
        await db.flush()
        try:
            await store.delete(old_key)
        except StorageUnavailableError:
            log.warning("speaking.delete_failed", key=old_key)
    key = f"speaking/{user_id}/{session.id}/{part_no}-{question_no}-{new_id()}.{MIME_EXT[kind]}"
    recording = SpeakingRecording(
        session_id=session.id,
        part_no=part_no,
        question_no=question_no,
        question_text=item["text"],
        storage_key=key,
        mime_type=kind,
        size_bytes=size_bytes,
        sha256=sha256.lower(),
        duration_ms=duration_ms,
    )
    db.add(recording)
    await db.flush()
    await db.refresh(recording)
    try:
        url = await store.presign_put(key, kind)
    except StorageUnavailableError as exc:
        raise RecordingStorageUnavailableError() from exc
    return recording, url


async def _owned_recording(
    db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID, recording_id: uuid.UUID
) -> tuple[SpeakingSession, SpeakingRecording]:
    session = await _owned(db, user_id, session_id, lock=True)
    recording = await db.scalar(
        select(SpeakingRecording).where(
            SpeakingRecording.id == recording_id, SpeakingRecording.session_id == session.id
        )
    )
    if recording is None:
        raise SessionNotFoundError()
    return session, recording


async def complete_recording(
    db: AsyncSession,
    store: ObjectStorage,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    recording_id: uuid.UUID,
) -> tuple[SpeakingRecording, str | None]:
    """Verify the uploaded object. Returns (recording, rejection reason or None)."""
    session, recording = await _owned_recording(db, user_id, session_id, recording_id)
    if session.status not in (SessionStatus.RECORDING.value, SessionStatus.LIVE.value):
        raise SessionLockedError()
    if recording.status == RecordingStatus.READY.value:
        return recording, None
    try:
        info = await store.inspect(recording.storage_key, max_bytes=MAX_RECORDING_BYTES)
    except StorageUnavailableError as exc:
        raise RecordingStorageUnavailableError() from exc
    reason = None
    if info is None:
        reason = "The recording was not uploaded."
    elif info.size_bytes != recording.size_bytes or info.sha256 != recording.sha256:
        reason = "The uploaded audio does not match what was recorded."
    elif not signature_ok(recording.mime_type, info.head):
        reason = "The file is not a supported audio recording."
    if reason is None:
        recording.status = RecordingStatus.READY.value
    else:
        recording.status = RecordingStatus.FAILED.value
        if info is not None:
            try:
                await store.delete(recording.storage_key)
            except StorageUnavailableError:
                log.warning("speaking.delete_failed", key=recording.storage_key)
    await db.flush()
    await db.refresh(recording)
    return recording, reason


async def playback_key(
    db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID, recording_id: uuid.UUID
) -> tuple[str, str]:
    session = await _owned(db, user_id, session_id)
    recording = await db.scalar(
        select(SpeakingRecording).where(
            SpeakingRecording.id == recording_id,
            SpeakingRecording.session_id == session.id,
            SpeakingRecording.status == RecordingStatus.READY.value,
        )
    )
    if recording is None:
        raise SessionNotFoundError()
    return recording.storage_key, recording.mime_type


def _queue(db: AsyncSession, session_id: uuid.UUID, key: uuid.UUID, user_id: uuid.UUID) -> None:
    evaluation = SpeakingEvaluation(
        id=new_id(),
        session_id=session_id,
        status=EvaluationStatus.QUEUED.value,
        idempotency_key=key,
        requested_by=user_id,
    )
    db.add(evaluation)
    enqueue(db, TOPIC, {"evaluation_id": str(evaluation.id)})


async def submit(
    db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID, *, key: uuid.UUID
) -> SpeakingSession:
    session, items, recordings, _ = await session_detail(db, user_id, session_id)
    session = await _owned(db, user_id, session_id, lock=True)
    if session.kind == "room":
        raise SessionLockedError("Rooms finish through the room, not by submitting.")
    if session.status == SessionStatus.SUBMITTED.value:
        if session.submit_key == key:
            return session
        raise SessionLockedError()
    ready = {(r.part_no, r.question_no) for r in recordings if r.status == RecordingStatus.READY}
    if any((i["part_no"], i["question_no"]) not in ready for i in items):
        raise RecordingsIncompleteError()
    session.status = SessionStatus.SUBMITTED.value
    session.submit_key = key
    session.submitted_at = _now()
    session.audio_purge_after = _now() + timedelta(days=AUDIO_RETENTION_DAYS)
    _queue(db, session.id, key, user_id)
    await db.flush()
    await db.refresh(session)
    return session


async def latest_evaluation(db: AsyncSession, session_id: uuid.UUID) -> SpeakingEvaluation | None:
    return await db.scalar(
        select(SpeakingEvaluation)
        .where(SpeakingEvaluation.session_id == session_id)
        .order_by(SpeakingEvaluation.created_at.desc(), SpeakingEvaluation.id.desc())
        .limit(1)
    )


async def retry(
    db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID, *, key: uuid.UUID
) -> None:
    session = await _owned(db, user_id, session_id, lock=True)
    same = await db.scalar(
        select(SpeakingEvaluation.id).where(SpeakingEvaluation.idempotency_key == key)
    )
    if same is not None:
        return
    latest = await latest_evaluation(db, session.id)
    if session.status not in (SessionStatus.SUBMITTED.value, SessionStatus.COMPLETED.value) or (
        latest is not None and latest.status not in RETRYABLE
    ):
        raise EvaluationNotRetryableError()
    _queue(db, session.id, key, user_id)
    await db.flush()


async def model_answers(db: AsyncSession, session: SpeakingSession) -> list[dict[str, Any]]:
    if session.status not in (SessionStatus.SUBMITTED.value, SessionStatus.COMPLETED.value):
        return []
    out: list[dict[str, Any]] = []
    for part in MODE_PARTS[session.mode]:
        for answer in await content.productive.model_answers(
            db, session.test_version_id, "speaking", part
        ):
            out.append({**answer, "part_no": part})
    return out


async def rubric_names(db: AsyncSession, rubric_id: uuid.UUID | None) -> dict[str, str]:
    if rubric_id is None:
        return {}
    rubric = await content.rubrics.get_rubric(db, rubric_id)
    return {c["code"]: c["name"] for c in rubric.criteria}


# ------------------------------------------------------------------------------ evaluation
async def _answers_from_turns(db: AsyncSession, session_id: uuid.UUID) -> list[SpokenAnswer]:
    from app.modules.speaking.models import SpeakingTurn

    rows = list(
        await db.scalars(
            select(SpeakingTurn)
            .where(SpeakingTurn.session_id == session_id, SpeakingTurn.speaker != "system")
            .order_by(SpeakingTurn.seq)
        )
    )
    answers: list[SpokenAnswer] = []
    question = ""
    for t in rows:
        if t.speaker == "examiner":
            question = t.text
        elif t.text.strip():
            words = len(t.text.split())
            answers.append(SpokenAnswer(t.part_no or 1, question, t.text, max(1000, words * 400)))
    return answers


async def handle_evaluate(ctx: OutboxContext, payload: dict[str, Any]) -> HandlerResult:
    evaluation_id = uuid.UUID(str(payload["evaluation_id"]))
    async with ctx.session_factory() as db, db.begin():
        evaluation = await db.scalar(
            select(SpeakingEvaluation)
            .where(SpeakingEvaluation.id == evaluation_id)
            .with_for_update()
        )
        if evaluation is None or evaluation.status not in (
            EvaluationStatus.QUEUED.value,
            EvaluationStatus.RUNNING.value,
        ):
            return "skipped"
        # A long AI call can outlive the outbox lease: never run the same evaluation twice
        # concurrently. A run that started long ago is treated as crashed and resumed.
        if (
            evaluation.status == EvaluationStatus.RUNNING.value
            and evaluation.started_at is not None
            and evaluation.started_at > _now() - STALE_RUN
        ):
            return "skipped"
        rubric = await content.rubrics.published_rubric(db, "speaking")
        evaluation.status = EvaluationStatus.RUNNING.value
        evaluation.attempt_count += 1
        evaluation.started_at = _now()
        evaluation.rubric_version_id = rubric.id if rubric else None
        criteria = (
            [
                RubricCriterion(c.code, c.name, c.description, c.bands)
                for c in content.rubrics.criteria_view(rubric)
            ]
            if rubric
            else []
        )
        recordings = list(
            await db.scalars(
                select(SpeakingRecording)
                .where(
                    SpeakingRecording.session_id == evaluation.session_id,
                    SpeakingRecording.status == RecordingStatus.READY.value,
                )
                .order_by(SpeakingRecording.part_no, SpeakingRecording.question_no)
            )
        )
        snapshot = [
            (r.id, r.part_no, r.question_text, r.storage_key, r.duration_ms, r.transcript)
            for r in recordings
        ]
        spoken: list[SpokenAnswer] = []
        if not snapshot:  # live room: the examiner conversation was transcribed in real time
            spoken = await _answers_from_turns(db, evaluation.session_id)
    wired = ai.providers(ctx.settings)
    outcome: tuple[EvaluationStatus, str | None, str | None] | None = None
    result = None
    transcripts: dict[uuid.UUID, str] = {}
    if wired.llm is None or (wired.stt is None and not spoken):
        outcome = (
            EvaluationStatus.UNAVAILABLE,
            "provider_not_configured",
            "AI evaluation is not available yet: no speech-to-text or AI provider is configured.",
        )
    elif not criteria:
        outcome = (
            EvaluationStatus.UNAVAILABLE,
            "rubric_not_published",
            "AI evaluation is not available yet: no Speaking rubric has been published.",
        )
    else:
        try:
            store = ObjectStorage(ctx.settings)
            answers = list(spoken)
            bands: list[float] = []
            for rec_id, part_no, question, key, duration, transcript in snapshot:
                audio: bytes | None = None
                if transcript is None:
                    if wired.stt is None:
                        raise StorageUnavailableError("no speech-to-text provider")
                    audio = await store.read(key, max_bytes=MAX_RECORDING_BYTES)
                    transcript = await wired.stt.transcribe(
                        audio, language="en", correlation_id=str(evaluation_id)
                    )
                    transcripts[rec_id] = transcript
                if wired.pronunciation is not None:
                    audio = audio or await store.read(key, max_bytes=MAX_RECORDING_BYTES)
                    scores = await wired.pronunciation.assess(
                        audio, reference_text=transcript, correlation_id=str(evaluation_id)
                    )
                    if "band" in scores:
                        bands.append(float(scores["band"]))
                answers.append(SpokenAnswer(part_no, question, transcript, duration))
            pr_band = overall_band(bands) if bands else None
            result = await evaluate_speaking(
                wired.llm,
                answers=answers,
                rubric=criteria,
                correlation_id=str(evaluation_id),
                model_name=wired.llm_model,
                pronunciation=wired.pronunciation if pr_band is not None else None,
                pronunciation_band=pr_band,
            )
        except InputRejectedError as exc:
            outcome = (EvaluationStatus.REJECTED_INPUT, exc.code, str(exc))
        except (
            EvaluationOutputError,
            ValidationError,
            StorageUnavailableError,
            GeminiError,
            httpx.HTTPError,
            TimeoutError,
            OSError,
        ) as exc:
            log.warning(
                "speaking.evaluate.failed", evaluation=str(evaluation_id), error=type(exc).__name__
            )
            outcome = (EvaluationStatus.FAILED, "provider_error", type(exc).__name__)
    async with ctx.session_factory() as db, db.begin():
        for rec_id, text in transcripts.items():
            recording = await db.get(SpeakingRecording, rec_id)
            if recording is not None:
                recording.transcript = text
        evaluation = await db.get_one(SpeakingEvaluation, evaluation_id, with_for_update=True)
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
            evaluation.status = EvaluationStatus.SUCCEEDED.value
            evaluation.finished_at = _now()
        elif outcome is not None:
            status, code, message = outcome
            evaluation.error_code = code
            if status is EvaluationStatus.FAILED and evaluation.attempt_count < MAX_EVAL_ATTEMPTS:
                evaluation.status = EvaluationStatus.QUEUED.value
                enqueue(db, TOPIC, {"evaluation_id": str(evaluation.id)})
            else:
                evaluation.status = status.value
                evaluation.error_message = message
                evaluation.finished_at = _now()
    return "sent"
