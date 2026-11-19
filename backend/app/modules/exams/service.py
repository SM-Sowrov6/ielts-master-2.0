"""Listening attempts (docs/EXAMINATION_ENGINE_DESIGN.md), Listening-scoped implementation.

- Create (idempotent per client key; one open exam-mode attempt per user+template+version) pins
  the published version and snapshots the template rules + question manifest.
- Start sets the server-authoritative start/deadline and issues the writer lease (ADR-013):
  `writer_epoch` + a random token stored only as a SHA-256 hash. Resume (takeover) bumps the epoch.
- Autosave: one short transaction holding `FOR SHARE` on the attempt row; checks owner, status,
  lease and deadline (+ grace); revision-guarded UPSERT, so retries/out-of-order writes are no-ops.
- Submit: `FOR UPDATE` (waits for in-flight saves), idempotent by `Idempotency-Key`, applies final
  answers within deadline + grace, scores every manifest question with the content handlers and
  completes the attempt in the same transaction (objective modules need no async step yet).
- Expiry: checked lazily on every attempt read, and by the outbox worker's sweeper.
Answer keys never enter this module: scoring and review data come from content.api.
"""

import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, select, text, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit import api as audit
from app.modules.content import api as content
from app.modules.exams.errors import (
    AttemptNotFoundError,
    AttemptStateError,
    AttemptSubmittedError,
    AudioUnavailableError,
    DeadlinePassedError,
    EntitlementRequiredError,
    ModeNotAllowedError,
    OpenExamAttemptExistsError,
    QuestionNotInAttemptError,
    ResponseInvalidError,
    SubmitKeyConflictError,
    SupersededSessionError,
    TestUnavailableError,
    WriterTokenInvalidError,
)
from app.modules.exams.models import (
    OPEN_STATUSES,
    AttemptAnswer,
    AttemptMode,
    AttemptResult,
    AttemptSection,
    AttemptStatus,
    ExamAttempt,
    ExamTemplate,
    QuestionScore,
)
from app.shared.ids import new_id

# Module -> exam template (seeded by migrations 0009 / 0010).
TEMPLATES = {"listening": "listening_only", "reading": "reading_only"}
TEMPLATE_CODE = TEMPLATES["listening"]
MODULE = "listening"
FULL_MODULE_QUESTIONS = 40  # band tables apply only to a complete 40-question module
MAX_RESPONSE_BYTES = 2048


def utcnow() -> datetime:
    return datetime.now(UTC)


def _hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def rules_of(attempt: ExamAttempt) -> dict[str, Any]:
    rules: dict[str, Any] = attempt.config_snapshot["rules"]
    return rules


def grace(attempt: ExamAttempt) -> timedelta:
    return timedelta(seconds=int(rules_of(attempt)["submission"].get("grace_seconds", 30)))


def manifest(attempt: ExamAttempt) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = attempt.config_snapshot["items"]
    return items


async def _audit(db: AsyncSession, action: str, attempt: ExamAttempt, **changes: Any) -> None:
    await audit.record(
        db,
        actor_id=attempt.user_id,
        action=action,
        entity_type="exam_attempt",
        entity_id=attempt.id,
        changes=changes,
    )


async def _template(db: AsyncSession, module: str = MODULE) -> ExamTemplate:
    template = await db.scalar(
        select(ExamTemplate).where(ExamTemplate.code == TEMPLATES[module], ExamTemplate.is_active)
    )
    if template is None:  # pragma: no cover - seeded by migrations
        raise TestUnavailableError("The exam template is not configured.")
    return template


def module_of(attempt: ExamAttempt) -> str:
    return str(attempt.config_snapshot.get("module", MODULE))


def time_limit_seconds(timing: dict[str, Any]) -> int:
    """Module time + transfer time (Listening snapshots use `listening_seconds`)."""
    base = timing.get("module_seconds", timing.get("listening_seconds", 0))
    return int(base) + int(timing.get("transfer_time_seconds", 0))


async def template_modes(
    db: AsyncSession, module: str = MODULE
) -> tuple[list[str], str, dict[str, Any]]:
    t = await _template(db, module)
    return list(t.allowed_modes), t.default_mode, t.rules


# ------------------------------------------------------------------------------ lookup
async def _get(
    db: AsyncSession, user_id: uuid.UUID, attempt_id: uuid.UUID, *, lock: str | None = None
) -> ExamAttempt:
    query = select(ExamAttempt).where(ExamAttempt.id == attempt_id, ExamAttempt.user_id == user_id)
    if lock == "update":
        query = query.with_for_update()
    elif lock == "share":
        query = query.with_for_update(read=True)
    attempt = await db.scalar(query)
    if attempt is None:
        raise AttemptNotFoundError()
    return attempt


def _expired(attempt: ExamAttempt, now: datetime) -> bool:
    return (
        attempt.status == AttemptStatus.IN_PROGRESS
        and attempt.deadline_at is not None
        and now > attempt.deadline_at + grace(attempt)
    )


async def get_attempt(db: AsyncSession, user_id: uuid.UUID, attempt_id: uuid.UUID) -> ExamAttempt:
    """Owner's attempt; an exam past deadline + grace is auto-submitted first (lazy expiry)."""
    attempt = await _get(db, user_id, attempt_id)
    if _expired(attempt, utcnow()):
        attempt = await _get(db, user_id, attempt_id, lock="update")
        if _expired(attempt, utcnow()):
            await _finalize(db, attempt, submitted_by="deadline")
    return attempt


# ------------------------------------------------------------------------------ create/start
@dataclass(frozen=True)
class Lease:
    epoch: int
    token: str


async def create_attempt(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    test_id: uuid.UUID,
    mode: str,
    idempotency_key: uuid.UUID,
    module: str = MODULE,
) -> ExamAttempt:
    existing = await db.scalar(
        select(ExamAttempt).where(
            ExamAttempt.user_id == user_id, ExamAttempt.create_idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        return existing  # a retried or double-clicked "Start"
    template = await _template(db, module)
    if mode not in template.allowed_modes:
        raise ModeNotAllowedError()
    try:
        test = await content.delivery.published_listening_test(db, test_id, module)
    except content.ContentNotFoundError as exc:
        raise TestUnavailableError() from exc
    if test.is_premium:
        # Plans/entitlements (Phase 8) do not exist yet: premium content cannot be started.
        raise EntitlementRequiredError()
    if mode == AttemptMode.EXAM:
        open_id = await db.scalar(
            select(ExamAttempt.id).where(
                ExamAttempt.user_id == user_id,
                ExamAttempt.template_id == template.id,
                ExamAttempt.test_version_id == test.version_id,
                ExamAttempt.mode == AttemptMode.EXAM.value,
                ExamAttempt.status.in_(OPEN_STATUSES),
            )
        )
        if open_id is not None:
            raise OpenExamAttemptExistsError(str(open_id))
    items = await content.delivery.listening_manifest(db, test.version_id)
    if not items:
        raise TestUnavailableError("This test has no questions.")
    attempt = ExamAttempt(
        id=new_id(),
        user_id=user_id,
        template_id=template.id,
        test_id=test.test_id,
        test_version_id=test.version_id,
        mode=mode,
        status=AttemptStatus.CREATED.value,
        create_idempotency_key=idempotency_key,
        config_snapshot={
            "template": template.code,
            "module": module,
            "rules": template.rules[mode],
            "test": {"title": test.title, "code": test.code, "book_title": test.book_title},
            "items": [
                {
                    "question_id": str(i.question_id),
                    "section_id": str(i.section_id),
                    "section_no": i.section_no,
                    "question_type": i.question_type,
                    "number_from": i.number_from,
                    "number_to": i.number_to,
                    "marks": i.marks,
                }
                for i in items
            ],
        },
    )
    sections = {(i.section_id, i.section_no) for i in items}
    try:
        async with db.begin_nested():
            db.add(attempt)
            await db.flush()
            for section_id, section_no in sorted(sections, key=lambda s: s[1]):
                db.add(
                    AttemptSection(
                        attempt_id=attempt.id, section_id=section_id, section_no=section_no
                    )
                )
            await db.flush()
    except IntegrityError as exc:  # a concurrent create with the same key / open exam attempt
        winner = await db.scalar(
            select(ExamAttempt).where(
                ExamAttempt.user_id == user_id,
                (ExamAttempt.create_idempotency_key == idempotency_key)
                | and_(
                    ExamAttempt.test_version_id == test.version_id,
                    ExamAttempt.mode == AttemptMode.EXAM.value,
                    ExamAttempt.status.in_(OPEN_STATUSES),
                ),
            )
        )
        if winner is None:
            raise
        if winner.create_idempotency_key == idempotency_key:
            return winner
        raise OpenExamAttemptExistsError(str(winner.id)) from exc
    await _audit(db, "exams.attempt.created", attempt, mode=mode, test_id=str(test.test_id))
    return attempt


def _new_lease(attempt: ExamAttempt) -> Lease:
    token = secrets.token_urlsafe(32)
    attempt.writer_epoch = attempt.writer_epoch + 1
    attempt.writer_token_hash = _hash(token)
    return Lease(attempt.writer_epoch, token)


async def start_attempt(
    db: AsyncSession, user_id: uuid.UUID, attempt_id: uuid.UUID
) -> tuple[ExamAttempt, Lease]:
    attempt = await _get(db, user_id, attempt_id, lock="update")
    if attempt.status != AttemptStatus.CREATED:
        # The lease token was issued once and is stored only as a hash: use resume instead.
        raise AttemptStateError(attempt.status, "The attempt has already started.")
    now = utcnow()
    timing = rules_of(attempt)["timing"]
    attempt.status = AttemptStatus.IN_PROGRESS.value
    attempt.started_at = now
    attempt.deadline_at = (
        now + timedelta(seconds=time_limit_seconds(timing)) if timing.get("enforce") else None
    )
    lease = _new_lease(attempt)
    await _audit(db, "exams.attempt.started", attempt, deadline_at=str(attempt.deadline_at))
    await db.flush()
    return attempt, lease


async def resume_attempt(
    db: AsyncSession, user_id: uuid.UUID, attempt_id: uuid.UUID
) -> tuple[ExamAttempt, Lease]:
    """Explicit takeover ("continue on this device"): older leases become read-only."""
    attempt = await _get(db, user_id, attempt_id, lock="update")
    if _expired(attempt, utcnow()):
        await _finalize(db, attempt, submitted_by="deadline")
    if attempt.status != AttemptStatus.IN_PROGRESS:
        raise AttemptStateError(attempt.status, "Only a running attempt can be continued.")
    lease = _new_lease(attempt)
    await _audit(db, "exams.attempt.resumed", attempt, writer_epoch=lease.epoch)
    await db.flush()
    return attempt, lease


# ------------------------------------------------------------------------------ answers
@dataclass(frozen=True)
class AnswerIn:
    question_id: uuid.UUID
    response: dict[str, Any] | None
    client_revision: int
    flagged: bool = False


def validate_response(response: Any) -> dict[str, Any] | None:
    """Shape check only (correctness is decided by the type handler at scoring time)."""
    if response is None:
        return None
    if not isinstance(response, dict) or len(json.dumps(response)) > MAX_RESPONSE_BYTES:
        raise ResponseInvalidError()
    keys = set(response)
    choice = response.get("choice")
    choices = response.get("choices")
    text_value = response.get("text")
    if keys == {"choice"} and isinstance(choice, str) and 0 < len(choice) <= 20:
        return response
    if (
        keys == {"choices"}
        and isinstance(choices, list)
        and 0 < len(choices) <= 10
        and all(isinstance(v, str) and 0 < len(v) <= 20 for v in choices)
    ):
        return response
    if keys == {"text"} and isinstance(text_value, str) and len(text_value) <= 200:
        return response
    raise ResponseInvalidError()


def _check_lease(attempt: ExamAttempt, epoch: int, token: str) -> None:
    if epoch != attempt.writer_epoch:
        raise SupersededSessionError()
    if attempt.writer_token_hash is None or not secrets.compare_digest(
        attempt.writer_token_hash, _hash(token)
    ):
        raise WriterTokenInvalidError()


@dataclass(frozen=True)
class StoredAnswer:
    question_id: uuid.UUID
    response: dict[str, Any] | None
    writer_epoch: int
    client_revision: int
    flagged: bool
    saved_at: datetime


async def _upsert(
    db: AsyncSession, attempt: ExamAttempt, items: list[AnswerIn], *, after_deadline: bool
) -> None:
    if not items:
        return
    stmt = insert(AttemptAnswer).values(
        [
            {
                "attempt_id": attempt.id,
                "question_id": i.question_id,
                "response": i.response,
                "writer_epoch": attempt.writer_epoch,
                "client_revision": i.client_revision,
                "flagged": i.flagged,
                "saved_after_deadline": after_deadline,
                "saved_at": func.now(),
            }
            for i in items
        ]
    )
    excluded = stmt.excluded
    stmt = stmt.on_conflict_do_update(
        index_elements=[AttemptAnswer.attempt_id, AttemptAnswer.question_id],
        set_={
            "response": excluded.response,
            "writer_epoch": excluded.writer_epoch,
            "client_revision": excluded.client_revision,
            "flagged": excluded.flagged,
            "saved_after_deadline": excluded.saved_after_deadline,
            "saved_at": func.now(),
        },
        # Highest (epoch, revision) wins: retried or out-of-order writes change nothing.
        where=tuple_(excluded.writer_epoch, excluded.client_revision)
        > tuple_(AttemptAnswer.writer_epoch, AttemptAnswer.client_revision),
    )
    await db.execute(stmt)


def _prepare(attempt: ExamAttempt, raw: list[AnswerIn]) -> list[AnswerIn]:
    allowed = {item["question_id"] for item in manifest(attempt)}
    prepared: dict[uuid.UUID, AnswerIn] = {}
    for item in raw:
        if str(item.question_id) not in allowed:
            raise QuestionNotInAttemptError()
        clean = AnswerIn(
            item.question_id, validate_response(item.response), item.client_revision, item.flagged
        )
        current = prepared.get(item.question_id)
        if current is None or clean.client_revision > current.client_revision:
            prepared[item.question_id] = clean
    return list(prepared.values())


async def save_answers(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    attempt_id: uuid.UUID,
    writer_epoch: int,
    writer_token: str,
    answers: list[AnswerIn],
) -> tuple[ExamAttempt, list[StoredAnswer]]:
    attempt = await _get(db, user_id, attempt_id, lock="share")
    if attempt.status in (AttemptStatus.SUBMITTED, AttemptStatus.COMPLETED):
        raise AttemptSubmittedError(attempt.status)
    if attempt.status != AttemptStatus.IN_PROGRESS:
        raise AttemptStateError(attempt.status, "Start the attempt first.")
    _check_lease(attempt, writer_epoch, writer_token)
    now = utcnow()
    late = attempt.deadline_at is not None and now > attempt.deadline_at
    if late and now > attempt.deadline_at + grace(attempt):  # type: ignore[operator]
        raise DeadlinePassedError()
    items = _prepare(attempt, answers)
    await _upsert(db, attempt, items, after_deadline=late)
    stored = await stored_answers(db, attempt.id, [i.question_id for i in items])
    return attempt, stored


async def stored_answers(
    db: AsyncSession, attempt_id: uuid.UUID, question_ids: list[uuid.UUID] | None = None
) -> list[StoredAnswer]:
    query = select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt_id)
    if question_ids is not None:
        query = query.where(AttemptAnswer.question_id.in_(question_ids))
    return [
        StoredAnswer(
            a.question_id, a.response, a.writer_epoch, a.client_revision, a.flagged, a.saved_at
        )
        for a in await db.scalars(query)
    ]


# ------------------------------------------------------------------------------ submit/score
async def submit_attempt(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    attempt_id: uuid.UUID,
    idempotency_key: uuid.UUID,
    writer_epoch: int,
    writer_token: str,
    final_answers: list[AnswerIn],
) -> ExamAttempt:
    attempt = await _get(db, user_id, attempt_id, lock="update")
    if attempt.status in (AttemptStatus.SUBMITTED, AttemptStatus.COMPLETED):
        if attempt.submit_idempotency_key == idempotency_key:
            return attempt  # retried submit: same outcome
        raise SubmitKeyConflictError()
    if attempt.status != AttemptStatus.IN_PROGRESS:
        raise AttemptStateError(attempt.status, "Start the attempt first.")
    now = utcnow()
    expired = _expired(attempt, now)
    if not expired:
        _check_lease(attempt, writer_epoch, writer_token)
        late = attempt.deadline_at is not None and now > attempt.deadline_at
        await _upsert(db, attempt, _prepare(attempt, final_answers), after_deadline=late)
    # Past deadline + grace only what the server already holds is scored (design §6).
    await _finalize(
        db,
        attempt,
        submitted_by="deadline" if expired else "candidate",
        idempotency_key=idempotency_key,
    )
    return attempt


async def _finalize(
    db: AsyncSession,
    attempt: ExamAttempt,
    *,
    submitted_by: str,
    idempotency_key: uuid.UUID | None = None,
) -> None:
    """Score every manifest question and complete the attempt (caller holds FOR UPDATE)."""
    answers = {a.question_id: a.response for a in await stored_answers(db, attempt.id)}
    scored = await content.delivery.score_responses(db, attempt.test_version_id, answers)
    in_manifest = {uuid.UUID(i["question_id"]): i["section_no"] for i in manifest(attempt)}
    rows = [
        {
            "attempt_id": attempt.id,
            "question_id": s.question_id,
            "section_no": in_manifest[s.question_id],
            "marks_awarded": s.marks_awarded,
            "marks_available": s.marks_available,
            "is_correct": s.is_correct,
            "reason": s.reason,
            "question_type": s.question_type,
            "scorer_version": s.scorer_version,
        }
        for s in scored
        if s.question_id in in_manifest
    ]
    if rows:
        await db.execute(insert(QuestionScore).values(rows).on_conflict_do_nothing())
    raw = sum(r["marks_awarded"] for r in rows)
    maximum = sum(r["marks_available"] for r in rows)
    band = (
        await content.delivery.listening_band(db, raw, module_of(attempt))
        if maximum == FULL_MODULE_QUESTIONS
        else None
    )
    await db.execute(
        insert(AttemptResult)
        .values(
            id=new_id(),
            attempt_id=attempt.id,
            module=module_of(attempt),
            raw_score=raw,
            max_score=maximum,
            band_estimate=band.band if band else None,
            band_table_id=band.table_id if band else None,
            source="auto",
        )
        .on_conflict_do_nothing()
    )
    now = utcnow()
    attempt.status = AttemptStatus.COMPLETED.value
    attempt.submitted_at = now
    attempt.completed_at = now
    attempt.submitted_by = submitted_by
    attempt.submit_idempotency_key = idempotency_key
    await _audit(
        db, "exams.attempt.submitted", attempt, submitted_by=submitted_by, raw=raw, max=maximum
    )
    await db.flush()


async def sweep_expired(db: AsyncSession, *, limit: int = 50) -> int:
    """Auto-submit exam attempts past deadline + grace (run by the outbox worker loop)."""
    ids = (
        await db.scalars(
            select(ExamAttempt.id)
            .where(
                ExamAttempt.status == AttemptStatus.IN_PROGRESS.value,
                ExamAttempt.deadline_at.is_not(None),
                ExamAttempt.deadline_at
                + func.make_interval(
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    func.coalesce(
                        ExamAttempt.config_snapshot["rules"]["submission"][
                            "grace_seconds"
                        ].as_integer(),
                        30,
                    ),
                )
                < func.now(),
                text(
                    "(config_snapshot->'rules'->'submission'->>'auto_submit_on_deadline')::boolean"
                ),
            )
            .order_by(ExamAttempt.deadline_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).all()
    for attempt_id in ids:
        attempt = await db.get_one(ExamAttempt, attempt_id)
        await _finalize(db, attempt, submitted_by="deadline")
    return len(ids)


# ------------------------------------------------------------------------------ results
@dataclass(frozen=True)
class Result:
    attempt: ExamAttempt
    raw_score: int
    max_score: int
    band_estimate: Any
    sections: list[dict[str, Any]]
    question_types: list[dict[str, Any]]


async def result(db: AsyncSession, user_id: uuid.UUID, attempt_id: uuid.UUID) -> Result:
    attempt = await get_attempt(db, user_id, attempt_id)
    if attempt.status != AttemptStatus.COMPLETED:
        raise AttemptStateError(attempt.status, "Results are available after submission.")
    row = await db.scalar(
        select(AttemptResult).where(
            AttemptResult.attempt_id == attempt.id, AttemptResult.module == module_of(attempt)
        )
    )
    if row is None:  # pragma: no cover - written in the same transaction as `completed`
        raise AttemptStateError(attempt.status, "The result is missing.")
    scores = list(
        await db.scalars(select(QuestionScore).where(QuestionScore.attempt_id == attempt.id))
    )
    answered = {a.question_id for a in await stored_answers(db, attempt.id) if a.response}

    def summary(key: str) -> list[dict[str, Any]]:
        groups: dict[Any, dict[str, Any]] = {}
        for s in scores:
            k = getattr(s, key)
            g = groups.setdefault(
                k, {key: k, "correct": 0, "marks": 0, "max": 0, "unanswered": 0, "questions": 0}
            )
            g["marks"] += s.marks_awarded
            g["max"] += s.marks_available
            g["questions"] += 1
            g["correct"] += int(s.is_correct)
            g["unanswered"] += int(s.question_id not in answered)
        return [groups[k] for k in sorted(groups)]

    return Result(
        attempt,
        row.raw_score,
        row.max_score,
        row.band_estimate,
        summary("section_no"),
        summary("question_type"),
    )


async def review(
    db: AsyncSession, user_id: uuid.UUID, attempt_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Responses, scores, accepted answers and explanations. Only after completion."""
    attempt = await get_attempt(db, user_id, attempt_id)
    if attempt.status != AttemptStatus.COMPLETED:
        raise AttemptStateError(attempt.status, "Answers are shown after submission.")
    keys = {
        r.question_id: r for r in await content.delivery.review_items(db, attempt.test_version_id)
    }
    scores = {
        s.question_id: s
        for s in await db.scalars(
            select(QuestionScore).where(QuestionScore.attempt_id == attempt.id)
        )
    }
    answers = {a.question_id: a.response for a in await stored_answers(db, attempt.id)}
    out = []
    for item in manifest(attempt):
        qid = uuid.UUID(item["question_id"])
        score = scores.get(qid)
        key = keys.get(qid)
        out.append(
            {
                **item,
                "response": answers.get(qid),
                "marks_awarded": score.marks_awarded if score else 0,
                "is_correct": bool(score and score.is_correct),
                "reason": score.reason if score else "no_response",
                "accepted": key.accepted if key else [],
                "explanation": key.explanation if key else None,
                "evidence_paragraph": key.evidence_paragraph if key else None,
            }
        )
    return out


@dataclass(frozen=True)
class HistoryRow:
    attempt: ExamAttempt
    raw_score: int | None
    max_score: int | None
    band_estimate: Any
    answered: int


async def history(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    test_id: uuid.UUID | None = None,
    limit: int = 50,
    module: str | None = None,
) -> list[HistoryRow]:
    answered = (
        select(func.count())
        .select_from(AttemptAnswer)
        .where(AttemptAnswer.attempt_id == ExamAttempt.id, AttemptAnswer.response.is_not(None))
        .correlate(ExamAttempt)
        .scalar_subquery()
    )
    query = (
        select(
            ExamAttempt,
            AttemptResult.raw_score,
            AttemptResult.max_score,
            AttemptResult.band_estimate,
            answered,
        )
        .outerjoin(
            AttemptResult,
            and_(
                AttemptResult.attempt_id == ExamAttempt.id,
                AttemptResult.module == ExamAttempt.config_snapshot["module"].astext,
            ),
        )
        .where(ExamAttempt.user_id == user_id)
        .order_by(ExamAttempt.created_at.desc())
        .limit(limit)
    )
    if test_id is not None:
        query = query.where(ExamAttempt.test_id == test_id)
    if module is not None:
        query = query.where(ExamAttempt.config_snapshot["module"].astext == module)
    rows = (await db.execute(query)).all()
    out = []
    now = utcnow()
    for attempt, raw, maximum, band, count in rows:
        if _expired(attempt, now):  # lazy expiry also from lists
            locked = await _get(db, user_id, attempt.id, lock="update")
            if _expired(locked, utcnow()):
                await _finalize(db, locked, submitted_by="deadline")
            res = await db.scalar(
                select(AttemptResult).where(AttemptResult.attempt_id == attempt.id)
            )
            raw, maximum, band = (
                (res.raw_score, res.max_score, res.band_estimate) if res else (None, None, None)
            )
        out.append(HistoryRow(attempt, raw, maximum, band, int(count or 0)))
    return out


# ------------------------------------------------------------------------------ audio
def media_ttl_seconds(attempt: ExamAttempt) -> int:
    """Audio/image URLs of an attempt live for its whole time limit plus a margin (design: exam
    audio TTL bound to the timed scope), so a long recording never expires mid-play."""
    return time_limit_seconds(rules_of(attempt)["timing"]) + 900


async def image_grant(
    db: AsyncSession, user_id: uuid.UUID, attempt_id: uuid.UUID, section_no: int, group_no: int
) -> tuple[str, str, int]:
    attempt = await get_attempt(db, user_id, attempt_id)
    try:
        image = await content.delivery.group_image(
            db, attempt.test_version_id, section_no, group_no
        )
    except content.ContentNotFoundError as exc:
        raise AttemptNotFoundError("No image for this question group.") from exc
    return image.storage_key, image.mime_type, media_ttl_seconds(attempt)


@dataclass(frozen=True)
class AudioGrant:
    storage_key: str
    mime_type: str
    ttl_seconds: int
    offset_ms: int
    plays_used: int
    max_plays: int | None
    allow_seek: bool


async def audio_grant(
    db: AsyncSession, user_id: uuid.UUID, attempt_id: uuid.UUID, section_no: int
) -> AudioGrant:
    """Exam mode: the first request starts the (single) play; later requests (reload) resume at
    the elapsed server offset instead of restarting. Practice: replay and seeking allowed.
    Play limits are a realism control, not anti-cheat (design §4)."""
    attempt = await get_attempt(db, user_id, attempt_id)
    if attempt.status not in (AttemptStatus.IN_PROGRESS, AttemptStatus.COMPLETED):
        raise AttemptStateError(attempt.status, "Start the attempt first.")
    section = await db.scalar(
        select(AttemptSection)
        .where(AttemptSection.attempt_id == attempt.id, AttemptSection.section_no == section_no)
        .with_for_update()
    )
    if section is None:
        raise AttemptNotFoundError("This section is not part of the attempt.")
    try:
        audio = await content.delivery.section_audio(db, attempt.test_version_id, section_no)
    except content.ContentNotFoundError as exc:
        raise AudioUnavailableError() from exc
    listening = rules_of(attempt)["listening"]
    exam_running = attempt.mode == AttemptMode.EXAM and attempt.status == AttemptStatus.IN_PROGRESS
    now = utcnow()
    offset = 0
    if exam_running and section.audio_started_at is not None:
        offset = int((now - section.audio_started_at).total_seconds() * 1000)
    else:
        section.audio_plays_used += 1
        if section.audio_started_at is None:
            section.audio_started_at = now
    await db.flush()
    return AudioGrant(
        audio.storage_key,
        audio.mime_type,
        media_ttl_seconds(attempt),
        offset,
        section.audio_plays_used,
        listening.get("max_plays") if exam_running else None,
        bool(listening.get("allow_seek")) or not exam_running,
    )


async def open_attempts_by_test(
    db: AsyncSession, user_id: uuid.UUID
) -> dict[uuid.UUID, ExamAttempt]:
    rows = await db.scalars(
        select(ExamAttempt)
        .where(ExamAttempt.user_id == user_id, ExamAttempt.status.in_(OPEN_STATUSES))
        .order_by(ExamAttempt.created_at.desc())
    )
    out: dict[uuid.UUID, ExamAttempt] = {}
    for a in rows:
        out.setdefault(a.test_id, a)
    return out


async def attempt_stats_by_test(
    db: AsyncSession, user_id: uuid.UUID
) -> dict[uuid.UUID, dict[str, Any]]:
    rows = await db.execute(
        select(
            ExamAttempt.test_id,
            func.count(ExamAttempt.id),
            func.max(AttemptResult.raw_score),
            func.max(ExamAttempt.completed_at),
        )
        .join(AttemptResult, AttemptResult.attempt_id == ExamAttempt.id)
        .where(ExamAttempt.user_id == user_id, ExamAttempt.status == AttemptStatus.COMPLETED.value)
        .group_by(ExamAttempt.test_id)
    )
    return {
        test_id: {"completed": count, "best_raw": best, "last_completed_at": last}
        for test_id, count, best, last in rows.all()
    }
