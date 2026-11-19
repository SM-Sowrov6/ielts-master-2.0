"""Candidate Speaking end to end against real PostgreSQL/Redis/MinIO: consented session, recordings
uploaded with presigned PUTs and verified server-side, submit, background evaluation.

STT and LLM are test doubles (no provider is contacted). Pronunciation is never inferred from
transcripts: without an audio assessor PR is `not_assessed` and no overall band is given."""

import hashlib
import os
import uuid
from typing import Any

import httpx
import pytest
import test_listening_admin_integration as _admin
from productive_fixtures import ESSAY, publish_productive, publish_rubric
from sqlalchemy import text
from test_listening_admin_integration import API, World
from test_writing_candidate_integration import FakeLLM, _drain, _post

from app.core import ai

# Shared fixtures (pytest discovers them as module attributes).
db_url = _admin.db_url
redis = _admin.redis
s3 = _admin.s3
world = _admin.world

pytestmark = pytest.mark.integration
S = "/speaking"


class FakeSTT:
    name = "fake-stt"

    def __init__(self) -> None:
        self.calls = 0

    async def transcribe(self, audio: bytes, *, language: str, correlation_id: str) -> str:
        assert audio.startswith(b"\x1a\x45\xdf\xa3")  # the real uploaded object was read
        self.calls += 1
        return ESSAY


SPOKEN = {
    "criteria": [
        {"code": c, "band": b, "rationale": "ok"} for c, b in (("FC", 6.5), ("LR", 6), ("GRA", 6))
    ],
    "summary": "Fluent with some hesitation.",
}


def webm(seed: int = 0) -> bytes:
    return b"\x1a\x45\xdf\xa3" + bytes([seed % 256]) * 64 + os.urandom(256)


async def _record(
    w: World, sid: str, part: int, q: int, data: bytes, *, declared: bytes | None = None
) -> httpx.Response:
    declared = declared if declared is not None else data
    ticket = await _post(
        w.student,
        f"{S}/sessions/{sid}/recordings",
        {
            "part_no": part,
            "question_no": q,
            "mime_type": "audio/webm;codecs=opus",
            "size_bytes": len(declared),
            "sha256": hashlib.sha256(declared).hexdigest(),
            "duration_ms": 30_000,
        },
    )
    assert ticket.status_code == 201, ticket.text
    t = ticket.json()
    async with httpx.AsyncClient() as raw:
        put = await raw.put(t["upload_url"], content=data, headers=t["headers"])
    assert put.status_code == 200, put.text
    return await _post(w.student, f"{S}/sessions/{sid}/recordings/{t['recording_id']}/complete")


async def _session(w: World, test_id: str, mode: str = "full") -> dict[str, Any]:
    r = await _post(
        w.student,
        f"{S}/sessions",
        {
            "test_id": test_id,
            "mode": mode,
            "voice_processing_consent": True,
            "audio_recording_consent": True,
        },
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


async def test_consent_recording_verification_and_submit(world: World) -> None:
    w = world
    test_id = (await publish_productive(w, "speaking"))["test"]["id"]
    detail = (await w.student.get(f"{S}/tests/{test_id}")).json()
    assert detail["parts"][1]["cue_card"]["prompt"].startswith("Describe")
    no_consent = await _post(
        w.student,
        f"{S}/sessions",
        {"test_id": test_id, "voice_processing_consent": False, "audio_recording_consent": True},
    )
    assert no_consent.status_code == 422
    session = await _session(w, test_id)
    sid = session["id"]
    assert [(i["part_no"], i["question_no"]) for i in session["items"]] == [
        (1, 1),
        (1, 2),
        (2, 1),
        (3, 1),
    ]
    consents = (
        (
            await w.sql(
                text(
                    "SELECT consent_type FROM user_consents uc JOIN speaking_sessions s "
                    "ON uc.id IN (s.processing_consent_id, s.recording_consent_id) "
                    "WHERE s.id = :id"
                ).bindparams(id=uuid.UUID(sid))
            )
        )
        .scalars()
        .all()
    )
    assert sorted(consents) == ["audio_recording", "voice_processing"]

    # Tampered or non-audio uploads are rejected and never count.
    tampered = await _record(w, sid, 1, 1, webm(1), declared=webm(2))
    assert tampered.status_code == 422
    assert tampered.json()["code"] == "recording_rejected"
    fake = b"not audio at all" * 10
    assert (await _record(w, sid, 1, 1, fake)).status_code == 422
    assert (
        await _post(
            w.student, f"{S}/sessions/{sid}/submit", None, **{"Idempotency-Key": str(uuid.uuid4())}
        )
    ).status_code == 409

    for part, q in ((1, 1), (1, 2), (2, 1), (3, 1)):
        done = await _record(w, sid, part, q, webm(part * 10 + q))
        assert done.status_code == 200, done.text
        assert done.json()["status"] == "ready"
    # Re-recording replaces the answer.
    assert (await _record(w, sid, 1, 1, webm(99))).status_code == 200
    rows = (
        await w.sql(
            text(
                "SELECT count(*) FROM speaking_recordings WHERE session_id = CAST(:id AS uuid)"
            ).bindparams(id=sid)
        )
    ).scalar()
    assert rows == 4

    current = (await w.student.get(f"{S}/sessions/{sid}")).json()
    rec_id = current["items"][0]["recording_id"]
    url = (await w.student.get(f"{S}/sessions/{sid}/recordings/{rec_id}/url")).json()["url"]
    async with httpx.AsyncClient() as raw:
        audio = await raw.get(url)
    assert audio.status_code == 200
    assert audio.content.startswith(b"\x1a\x45\xdf\xa3")
    # Another account cannot see the session or its audio.
    assert (await w.reviewer.get(f"{S}/sessions/{sid}")).status_code == 404
    assert (await w.reviewer.get(f"{S}/sessions/{sid}/recordings/{rec_id}/url")).status_code == 404

    key = str(uuid.uuid4())
    sub = await _post(w.student, f"{S}/sessions/{sid}/submit", None, **{"Idempotency-Key": key})
    assert sub.status_code == 200, sub.text
    body = sub.json()
    assert body["status"] == "submitted"
    assert body["audio_purge_after"] is not None
    assert body["evaluation"]["status"] == "queued"
    assert body["model_answers"][0]["band"] == 7.0
    assert (
        await _post(w.student, f"{S}/sessions/{sid}/submit", None, **{"Idempotency-Key": key})
    ).status_code == 200
    locked = await _post(
        w.student,
        f"{S}/sessions/{sid}/recordings",
        {
            "part_no": 1,
            "question_no": 1,
            "mime_type": "audio/webm",
            "size_bytes": 10,
            "sha256": "0" * 64,
            "duration_ms": 1000,
        },
    )
    assert locked.status_code == 409


async def test_evaluation_unavailable_then_transcribed_and_scored_without_inventing_pr(
    world: World,
) -> None:
    w = world
    test_id = (await publish_productive(w, "speaking"))["test"]["id"]
    session = await _session(w, test_id, "part1")
    sid = session["id"]
    for item in session["items"]:
        assert (
            await _record(w, sid, item["part_no"], item["question_no"], webm())
        ).status_code == 200
    ai.use_providers(ai.Providers())
    assert (
        await _post(
            w.student, f"{S}/sessions/{sid}/submit", None, **{"Idempotency-Key": str(uuid.uuid4())}
        )
    ).status_code == 200
    await _drain(w)
    got = (await w.student.get(f"{S}/sessions/{sid}")).json()
    assert got["evaluation"]["status"] == "unavailable"
    assert got["evaluation"]["band_overall"] is None

    rubrics = (await w.owner.get(f"{API}/rubrics?module=speaking")).json()
    if not any(r["status"] == "published" for r in rubrics):
        await publish_rubric(w, "speaking")
    stt = FakeSTT()
    ai.use_providers(ai.Providers(llm=FakeLLM(SPOKEN), llm_model="fake-1", stt=stt))
    try:
        retry = await _post(
            w.student,
            f"{S}/sessions/{sid}/evaluations",
            None,
            **{"Idempotency-Key": str(uuid.uuid4())},
        )
        assert retry.status_code == 202, retry.text
        await _drain(w)
        got = (await w.student.get(f"{S}/sessions/{sid}")).json()
        evaluation = got["evaluation"]
        assert evaluation["status"] == "succeeded", evaluation
        assert [c["code"] for c in evaluation["criteria"]] == ["FC", "LR", "GRA"]
        assert evaluation["not_assessed"] == ["PR"]
        assert evaluation["band_overall"] is None  # no overall without a pronunciation band
        assert stt.calls == len(session["items"])
        assert all(i["transcript"] == ESSAY for i in got["items"])
    finally:
        ai.use_providers(ai.Providers())
