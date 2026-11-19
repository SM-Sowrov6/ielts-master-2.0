"""Candidate Listening attempts against real PostgreSQL, Redis and MinIO.

A synthetic test (tests/listening_fixtures.py) is published through the real admin API (author +
a different reviewer), then a real student takes it. Requires the same variables as
test_listening_admin_integration.py.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from redis.asyncio import Redis
from sqlalchemy import text, update
from sqlalchemy.engine import make_url
from test_identity_integration import ALEMBIC_INI, Browser
from test_listening_admin_integration import (
    API,
    World,
    _env,
    _full_draft,
    _StudentEnv,
    admin_setup,
    close_world,
)

from app.modules.exams import api as exams_api
from app.modules.exams.models import ExamAttempt

pytestmark = pytest.mark.integration

# Correct responses for the synthetic test, by question number (see listening_fixtures.py).
TEXT = {
    1: "library", 2: "color", 3: "25", 4: "zebra", 5: "lamp", 9: "river", 10: "garden",
    15: "kitchen", 16: "office", 21: "survey", 22: "data", 23: "graph", 24: "monday",
    25: "budget", 26: "report", 27: "sample", 28: "result", 31: "energy", 32: "ocean",
    33: "wind", 34: "solar", 35: "cost", 36: "policy", 37: "valve", 38: "pipe", 39: "pump",
    40: "tank",
}  # fmt: skip
CHOICE = {
    6: "B",
    7: "B",
    8: "B",
    11: "A",
    12: "C",
    13: "E",
    14: "F",
    19: "C",
    20: "A",
    29: "B",
    30: "D",
}
MULTI = {17: ["A", "D"]}
SECRETS = ["the library", "colour", "Synthetic explanation", "accepted", "answer_keys", "canonical"]


def correct_response(number: int) -> dict[str, Any]:
    if number in TEXT:
        return {"text": TEXT[number]}
    if number in CHOICE:
        return {"choice": CHOICE[number]}
    return {"choices": MULTI[number]}


@pytest.fixture
def media() -> dict[str, str]:
    endpoint = _env("TEST_S3_ENDPOINT_URL")
    return {
        "s3_endpoint_url": endpoint,
        "s3_public_endpoint_url": endpoint,
        "s3_access_key_id": _env("TEST_S3_ACCESS_KEY_ID"),
        "s3_secret_access_key": _env("TEST_S3_SECRET_ACCESS_KEY"),
        "s3_bucket": "ielts-media-test",
    }


@pytest.fixture
def candidate_db(test_database_url: str) -> str:
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["configure_logger"] = False
    cfg.attributes["database_url"] = test_database_url
    command.upgrade(cfg, "head")
    return test_database_url


@pytest.fixture
async def published(
    candidate_db: str, test_redis_url: str, media: dict[str, str]
) -> AsyncIterator[Ctx]:
    test_database_url = candidate_db
    redis_url = make_url(test_redis_url).set(database="15").render_as_string(hide_password=False)
    client = Redis.from_url(redis_url)
    await client.flushdb()
    await client.aclose()
    world, app = await admin_setup(test_database_url, redis_url, media)
    saved = await _full_draft(world)
    vid = saved["document"]["version"]["id"]
    assert (await world.owner.post(f"{API}/versions/{vid}/submit")).status_code == 200
    ok = await world.reviewer.post(f"{API}/versions/{vid}/review", {"decision": "approved"})
    assert ok.status_code == 200
    pub = await world.owner.post(f"{API}/versions/{vid}/publish")
    assert pub.status_code == 200, pub.text
    student_env = _StudentEnv(app, app.state.settings)
    other = await student_env.student()
    ctx = Ctx(world, app, pub.json(), world.student, other)
    yield ctx
    await other.close()
    await close_world(world, app)


@dataclass
class Ctx:
    w: World
    app: Any
    doc: dict[str, Any]
    student: Browser
    other: Browser

    @property
    def test_id(self) -> str:
        return str(self.doc["test"]["id"])

    async def sql(self, statement: Any) -> Any:
        async with self.app.state.db_session_factory() as db, db.begin():
            return await db.execute(statement)


async def _post(b: Browser, path: str, body: Any = None, **headers: str) -> httpx.Response:
    token = b.client.cookies.get("ielts_csrf") or await b.csrf()
    return await b.client.post(
        f"/api/v1{path}", json=body, headers={"X-CSRF-Token": token, **headers}
    )


async def _put_answers(
    b: Browser, attempt: str, lease: dict[str, Any], answers: list[dict[str, Any]]
) -> httpx.Response:
    token = b.client.cookies.get("ielts_csrf") or await b.csrf()
    return await b.client.put(
        f"/api/v1/attempts/{attempt}/answers",
        json={"writer_epoch": lease["writer_epoch"], "answers": answers},
        headers={"X-CSRF-Token": token, "X-Writer-Token": lease["writer_token"]},
    )


async def _begin(
    c: Ctx, mode: str = "practice", b: Browser | None = None
) -> tuple[str, dict[str, Any]]:
    b = b or c.student
    created = await _post(
        b,
        "/attempts",
        {"test_id": c.test_id, "mode": mode},
        **{"Idempotency-Key": str(uuid.uuid4())},
    )
    assert created.status_code == 201, created.text
    attempt = created.json()["id"]
    lease = await _post(b, f"/attempts/{attempt}/start")
    assert lease.status_code == 200, lease.text
    return attempt, lease.json()


async def _questions(b: Browser, attempt: str) -> dict[int, str]:
    content = (await b.get(f"/attempts/{attempt}/content")).json()
    return {
        q["number_from"]: q["id"]
        for s in content["sections"]
        for g in s["groups"]
        for q in g["questions"]
    }


# --------------------------------------------------------------------------- catalogue
async def test_catalogue_lists_only_published_tests(published: Ctx) -> None:
    c = published
    assert (await c.w.anonymous.get("/listening/tests")).status_code == 401
    listed = (await c.student.get("/listening/tests")).json()
    ids = {t["test_id"] for t in listed}
    assert c.test_id in ids
    row = next(t for t in listed if t["test_id"] == c.test_id)
    assert row["questions"] == 40
    assert row["sections"] == 4
    assert row["locked"] is False
    assert row["progress"]["completed"] == 0
    # A draft-only test is neither listed nor reachable.
    draft = await c.w.owner.post(
        f"{API}/listening/tests",
        {"edition_id": c.w.edition_id, "code": f"D-{uuid.uuid4().hex[:5]}", "title": "Draft only"},
    )
    draft_test = draft.json()["test"]["id"]
    assert draft_test not in {
        t["test_id"] for t in (await c.student.get("/listening/tests")).json()
    }
    assert (await c.student.get(f"/listening/tests/{draft_test}")).status_code == 404
    created = await _post(
        c.student, "/attempts", {"test_id": draft_test}, **{"Idempotency-Key": str(uuid.uuid4())}
    )
    assert created.status_code == 404
    detail = (await c.student.get(f"/listening/tests/{c.test_id}")).json()
    assert [s["section_no"] for s in detail["section_list"]] == [1, 2, 3, 4]
    assert {m["mode"] for m in detail["modes"]} == {"practice", "exam"}
    exam = next(m for m in detail["modes"] if m["mode"] == "exam")
    assert exam == {
        "mode": "exam",
        "timed": True,
        "time_limit_seconds": 1920,
        "max_plays": 1,
        "allow_seek": False,
        "auto_submit": True,
    }
    assert "Internal synthetic note" not in json.dumps(detail)
    search = (await c.student.get("/listening/tests?search=zzz-no-match")).json()
    assert search == []


async def test_premium_tests_are_locked(published: Ctx) -> None:
    c = published
    await c.sql(text("UPDATE books SET is_premium = true"))
    try:
        row = next(
            t for t in (await c.student.get("/listening/tests")).json() if t["test_id"] == c.test_id
        )
        assert row["locked"] is True
        r = await _post(
            c.student, "/attempts", {"test_id": c.test_id}, **{"Idempotency-Key": str(uuid.uuid4())}
        )
        assert r.status_code == 403
        assert r.json()["code"] == "entitlement_required"
    finally:
        await c.sql(text("UPDATE books SET is_premium = false"))


# --------------------------------------------------------------------------- create/start
async def test_attempt_creation_is_idempotent_and_exam_mode_is_single(published: Ctx) -> None:
    c = published
    key = str(uuid.uuid4())
    first, second = await asyncio.gather(
        _post(c.student, "/attempts", {"test_id": c.test_id}, **{"Idempotency-Key": key}),
        _post(c.student, "/attempts", {"test_id": c.test_id}, **{"Idempotency-Key": key}),
    )
    assert {first.status_code, second.status_code} == {201}
    assert first.json()["id"] == second.json()["id"]  # double click / retry -> one attempt
    assert first.json()["status"] == "created"
    exam, lease = await _begin(c, "exam")
    again = await _post(
        c.student,
        "/attempts",
        {"test_id": c.test_id, "mode": "exam"},
        **{"Idempotency-Key": str(uuid.uuid4())},
    )
    assert again.status_code == 409
    assert again.json()["code"] == "attempt_open_exists"
    assert again.json()["attempt_id"] == exam
    state = (await c.student.get(f"/attempts/{exam}")).json()
    assert state["status"] == "in_progress"
    assert state["deadline_at"] is not None  # server-set: 30 min + 2 min transfer
    assert "writer_token" not in state
    twice = await _post(c.student, f"/attempts/{exam}/start")
    assert twice.status_code == 409  # the lease is issued once; resume takes over
    practice, _ = await _begin(c, "practice")
    assert (await c.student.get(f"/attempts/{practice}")).json()["deadline_at"] is None
    # Ownership: other students see nothing.
    for path in (f"/attempts/{exam}", f"/attempts/{exam}/content", f"/attempts/{exam}/answers"):
        assert (await c.other.get(path)).status_code == 404
    assert (await _post(c.other, f"/attempts/{exam}/start")).status_code == 404
    assert lease["writer_epoch"] == 1


async def test_attempt_content_never_contains_answer_keys(published: Ctx) -> None:
    c = published
    attempt, _ = await _begin(c)
    raw = (await c.student.get(f"/attempts/{attempt}/content")).text
    for secret in SECRETS:
        assert secret not in raw, secret
    detail = (await c.student.get(f"/listening/tests/{c.test_id}")).text
    for secret in SECRETS:
        assert secret not in detail, secret
    review = await c.student.get(f"/attempts/{attempt}/review")
    assert review.status_code == 409  # no keys before submission
    assert (await c.student.get(f"/attempts/{attempt}/result")).status_code == 409


# --------------------------------------------------------------------------- autosave
async def test_autosave_recovery_revisions_and_lease(published: Ctx) -> None:
    c = published
    attempt, lease = await _begin(c)
    q = await _questions(c.student, attempt)
    r = await _put_answers(
        c.student,
        attempt,
        lease,
        [{"question_id": q[1], "response": {"text": "first"}, "client_revision": 2}],
    )
    assert r.status_code == 200, r.text
    assert r.json()["stored"][0]["client_revision"] == 2
    stale = await _put_answers(
        c.student,
        attempt,
        lease,
        [{"question_id": q[1], "response": {"text": "older"}, "client_revision": 1}],
    )
    assert stale.status_code == 200
    assert stale.json()["stored"][0]["response"] == {"text": "first"}  # older request is a no-op
    # Recovery after a reload: the server is the source of truth.
    saved = (await c.student.get(f"/attempts/{attempt}/answers")).json()["answers"]
    assert saved == [r.json()["stored"][0]] or saved[0]["response"] == {"text": "first"}
    # Validation of shape and membership.
    bad = await _put_answers(
        c.student,
        attempt,
        lease,
        [{"question_id": q[1], "response": {"text": 5}, "client_revision": 3}],
    )
    assert bad.status_code == 422
    foreign = await _put_answers(
        c.student,
        attempt,
        lease,
        [{"question_id": str(uuid.uuid4()), "response": None, "client_revision": 3}],
    )
    assert foreign.status_code == 422
    assert foreign.json()["code"] == "question_not_in_attempt"
    wrong = await _put_answers(
        c.student,
        attempt,
        {**lease, "writer_token": "x" * 40},
        [{"question_id": q[1], "response": None, "client_revision": 9}],
    )
    assert wrong.status_code == 403
    # Takeover from another tab/device: the old lease can no longer write.
    resumed = (await _post(c.student, f"/attempts/{attempt}/resume")).json()
    assert resumed["writer_epoch"] == 2
    old = await _put_answers(
        c.student,
        attempt,
        lease,
        [{"question_id": q[1], "response": {"text": "late"}, "client_revision": 10}],
    )
    assert old.status_code == 409
    assert old.json()["code"] == "superseded_session"
    new = await _put_answers(
        c.student,
        attempt,
        resumed,
        [{"question_id": q[1], "response": {"text": "new device"}, "client_revision": 1}],
    )
    assert new.json()["stored"][0]["response"] == {"text": "new device"}  # higher epoch wins
    # Another student cannot write even with a valid-looking lease.
    assert (
        await _put_answers(
            c.other,
            attempt,
            resumed,
            [{"question_id": q[1], "response": None, "client_revision": 99}],
        )
    ).status_code == 404


async def test_concurrent_and_out_of_order_saves_keep_the_newest(published: Ctx) -> None:
    c = published
    attempt, lease = await _begin(c)
    q = await _questions(c.student, attempt)
    revisions = list(range(1, 21))
    import random

    random.shuffle(revisions)
    responses = await asyncio.gather(
        *(
            _put_answers(
                c.student,
                attempt,
                lease,
                [{"question_id": q[3], "response": {"text": f"v{n}"}, "client_revision": n}],
            )
            for n in revisions
        )
    )
    assert {r.status_code for r in responses} == {200}
    stored = (await c.student.get(f"/attempts/{attempt}/answers")).json()["answers"]
    assert stored[0]["response"] == {"text": "v20"}
    assert stored[0]["client_revision"] == 20


# --------------------------------------------------------------------------- submit/score
async def test_submission_scores_on_the_server_and_is_idempotent(published: Ctx) -> None:
    c = published
    attempt, lease = await _begin(c)
    q = await _questions(c.student, attempt)
    # 36 correct answers saved by autosave, 2 wrong, 2 left blank (Q39, Q40).
    answers = []
    for number in sorted(n for n in q if n < 39):
        response = correct_response(number)
        if number in (5, 12):
            response = {"text": "wrong"} if number == 5 else {"choice": "B"}
        answers.append({"question_id": q[number], "response": response, "client_revision": 1})
    for chunk in (answers[:20], answers[20:]):
        assert (await _put_answers(c.student, attempt, lease, chunk)).status_code == 200
    key = str(uuid.uuid4())
    final = {
        "writer_epoch": lease["writer_epoch"],
        "final_answers": [
            {"question_id": q[17], "response": {"choices": ["D", "A"]}, "client_revision": 5}
        ],
    }
    headers = {"Idempotency-Key": key, "X-Writer-Token": lease["writer_token"]}
    first, second = await asyncio.gather(
        _post(c.student, f"/attempts/{attempt}/submit", final, **headers),
        _post(c.student, f"/attempts/{attempt}/submit", final, **headers),
    )
    assert {first.status_code, second.status_code} == {200}
    assert first.json()["status"] == "completed"
    assert first.json()["submitted_by"] == "candidate"
    other_key = await _post(
        c.student,
        f"/attempts/{attempt}/submit",
        final,
        **{**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert other_key.status_code == 409
    after = await _put_answers(
        c.student,
        attempt,
        lease,
        [{"question_id": q[39], "response": {"text": "pump"}, "client_revision": 50}],
    )
    assert after.status_code == 409
    assert after.json()["code"] == "attempt_submitted"

    result = (await c.student.get(f"/attempts/{attempt}/result")).json()
    assert result["raw_score"] == 36  # 40 - 2 wrong - 2 blank (Q17-18 counts 2 marks)
    assert result["max_score"] == 40
    assert result["percentage"] == 90.0
    assert result["unanswered"] == 2
    assert result["incorrect"] == 2
    assert result["band_available"] is False  # no approved conversion table is seeded
    assert result["band_estimate"] is None
    assert sum(s["marks"] for s in result["sections"]) == 36
    assert {s["section_no"] for s in result["sections"]} == {1, 2, 3, 4}
    assert (await c.other.get(f"/attempts/{attempt}/result")).status_code == 404

    review = (await c.student.get(f"/attempts/{attempt}/review")).json()
    by_number = {i["number_from"]: i for i in review["items"]}
    assert by_number[1]["is_correct"] is True
    assert by_number[1]["accepted"][0][0] == "the library"
    assert by_number[1]["explanation"] is not None
    assert by_number[5]["is_correct"] is False
    assert by_number[5]["response"] == {"text": "wrong"}
    assert by_number[39]["reason"] == "no_response"
    assert by_number[17]["marks_awarded"] == 2
    assert (await c.other.get(f"/attempts/{attempt}/review")).status_code == 404
    history = (await c.student.get("/attempts")).json()["items"]
    row = next(h for h in history if h["id"] == attempt)
    assert row["raw_score"] == 36
    assert row["status"] == "completed"
    listed = next(
        t for t in (await c.student.get("/listening/tests")).json() if t["test_id"] == c.test_id
    )
    assert listed["progress"]["completed"] >= 1
    assert listed["progress"]["best_raw"] >= 36


async def test_band_estimate_uses_an_approved_table_only(published: Ctx) -> None:
    c = published
    table = uuid.uuid4()
    await c.sql(
        text(
            "INSERT INTO band_conversion_tables (id, module, variant, label, source, is_default) "
            "VALUES (:id, 'listening', 'common', 'Test table', 'synthetic test data', true)"
        ).bindparams(id=table)
    )
    await c.sql(
        text(
            "INSERT INTO band_conversion_rows (table_id, raw_min, raw_max, band) VALUES "
            "(:id, 0, 29, 5.0), (:id, 30, 40, 8.5)"
        ).bindparams(id=table)
    )
    try:
        attempt, lease = await _begin(c)
        q = await _questions(c.student, attempt)
        answers = [
            {"question_id": q[n], "response": correct_response(n), "client_revision": 1} for n in q
        ]
        for i in range(0, len(answers), 50):
            assert (
                await _put_answers(c.student, attempt, lease, answers[i : i + 50])
            ).status_code == 200
        r = await _post(
            c.student,
            f"/attempts/{attempt}/submit",
            {"writer_epoch": lease["writer_epoch"]},
            **{"Idempotency-Key": str(uuid.uuid4()), "X-Writer-Token": lease["writer_token"]},
        )
        assert r.status_code == 200
        result = (await c.student.get(f"/attempts/{attempt}/result")).json()
        assert result["raw_score"] == 40
        assert result["band_available"] is True
        assert result["band_estimate"] == "8.5"
    finally:
        await c.sql(text("DELETE FROM band_conversion_tables WHERE id = :id").bindparams(id=table))


# --------------------------------------------------------------------------- deadline
async def test_exam_deadline_grace_lazy_expiry_and_sweeper(published: Ctx) -> None:
    c = published
    attempt, lease = await _begin(c, "exam")
    q = await _questions(c.student, attempt)
    aid = uuid.UUID(attempt)
    # Within the grace window: accepted and flagged.
    await c.sql(
        update(ExamAttempt)
        .where(ExamAttempt.id == aid)
        .values(deadline_at=text("now() - interval '10 seconds'"))
    )
    late = await _put_answers(
        c.student,
        attempt,
        lease,
        [{"question_id": q[1], "response": {"text": "library"}, "client_revision": 1}],
    )
    assert late.status_code == 200
    flagged = (
        await c.sql(
            text(
                "SELECT saved_after_deadline FROM attempt_answers WHERE attempt_id = :a"
            ).bindparams(a=aid)
        )
    ).scalar_one()
    assert flagged is True
    # Past deadline + grace: writes refused, and the next read auto-submits what was saved.
    await c.sql(
        update(ExamAttempt)
        .where(ExamAttempt.id == aid)
        .values(deadline_at=text("now() - interval '5 minutes'"))
    )
    refused = await _put_answers(
        c.student,
        attempt,
        lease,
        [{"question_id": q[2], "response": {"text": "color"}, "client_revision": 1}],
    )
    assert refused.status_code == 409
    assert refused.json()["code"] == "attempt_deadline_passed"
    state = (await c.student.get(f"/attempts/{attempt}")).json()
    assert state["status"] == "completed"
    assert state["submitted_by"] == "deadline"
    assert (await c.student.get(f"/attempts/{attempt}/result")).json()["raw_score"] == 1

    # The sweeper auto-submits attempts nobody looks at any more.
    other, _ = await _begin(c, "exam", b=c.other)
    oid = uuid.UUID(other)
    await c.sql(
        update(ExamAttempt)
        .where(ExamAttempt.id == oid)
        .values(deadline_at=text("now() - interval '5 minutes'"))
    )
    async with c.app.state.db_session_factory() as db, db.begin():
        swept = await exams_api.sweep_expired(db)
    assert swept >= 1
    status = (
        await c.sql(
            text("SELECT status, submitted_by FROM exam_attempts WHERE id = :a").bindparams(a=oid)
        )
    ).one()
    assert tuple(status) == ("completed", "deadline")
    rows = (
        await c.sql(
            text("SELECT count(*) FROM question_scores WHERE attempt_id = :a").bindparams(a=oid)
        )
    ).scalar_one()
    assert rows == 39  # every manifest question gets an explicit score row


# --------------------------------------------------------------------------- audio
async def test_audio_is_delivered_through_short_lived_owner_only_urls(published: Ctx) -> None:
    c = published
    practice, _ = await _begin(c)
    grant = await _post(c.student, f"/attempts/{practice}/sections/1/audio-url")
    assert grant.status_code == 200, grant.text
    g = grant.json()
    assert g["allow_seek"] is True
    assert g["max_plays"] is None
    assert "X-Amz-Expires=2820" in g["url"]  # module limit (32 min) + 15 min margin
    image = await c.student.get(f"/attempts/{practice}/sections/2/groups/1/image-url")
    assert image.status_code == 200, image.text
    async with httpx.AsyncClient() as raw:
        assert (await raw.get(image.json()["url"])).content.startswith(bytes([0x89]) + b"PNG")
    other_image = await c.other.get(f"/attempts/{practice}/sections/2/groups/1/image-url")
    assert other_image.status_code == 404
    none = await c.student.get(f"/attempts/{practice}/sections/1/groups/1/image-url")
    assert none.status_code == 404
    async with httpx.AsyncClient() as raw:
        fetched = await raw.get(g["url"])
    assert fetched.status_code == 200
    assert fetched.content[:4] == b"RIFF"
    assert (await _post(c.other, f"/attempts/{practice}/sections/1/audio-url")).status_code == 404
    exam, _ = await _begin(c, "exam", b=c.other)
    first = (await _post(c.other, f"/attempts/{exam}/sections/2/audio-url")).json()
    assert first["offset_ms"] == 0
    assert first["allow_seek"] is False
    assert first["max_plays"] == 1
    await asyncio.sleep(0.3)
    reload = (await _post(c.other, f"/attempts/{exam}/sections/2/audio-url")).json()
    assert reload["offset_ms"] >= 250  # a reload resumes, it does not restart the recording
    assert reload["plays_used"] == 1


async def test_answers_are_never_lost_when_racing_submit(published: Ctx) -> None:
    c = published
    attempt, lease = await _begin(c)
    q = await _questions(c.student, attempt)
    numbers = list(q)[:20]
    saves = [
        _put_answers(
            c.student,
            attempt,
            lease,
            [{"question_id": q[n], "response": correct_response(n), "client_revision": 1}],
        )
        for n in numbers
    ]
    submit = _post(
        c.student,
        f"/attempts/{attempt}/submit",
        {"writer_epoch": lease["writer_epoch"]},
        **{"Idempotency-Key": str(uuid.uuid4()), "X-Writer-Token": lease["writer_token"]},
    )
    results = await asyncio.gather(*saves, submit)
    acknowledged = {n for n, r in zip(numbers, results[:-1], strict=True) if r.status_code == 200}
    assert results[-1].status_code == 200
    scored = (
        await c.sql(
            text(
                "SELECT question_id::text, marks_awarded FROM question_scores WHERE attempt_id = :a"
            ).bindparams(a=uuid.UUID(attempt))
        )
    ).all()
    awarded = {qid for qid, marks in scored if marks > 0}
    for n in acknowledged:  # every 200-acknowledged answer was scored
        assert q[n] in awarded, n
    stored = (
        await c.sql(
            text("SELECT count(*) FROM attempt_answers WHERE attempt_id = :a").bindparams(
                a=uuid.UUID(attempt)
            )
        )
    ).scalar_one()
    assert stored == len(acknowledged)
