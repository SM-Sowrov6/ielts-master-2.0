"""AI Speaking Room against real PostgreSQL/Redis/MinIO: admin examiner configuration (draft,
preview, publish protection), room creation, guided conduct from the frozen plan, verified
recordings per answer, transcript ordering, completion and pending evaluation, ownership, and the
internal live-event endpoint (disabled without a token; idempotent with one, via a fake adapter).

No voice provider and no AI model are contacted: the live path uses a test-double adapter."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import pytest
import test_listening_admin_integration as _admin
from productive_fixtures import publish_productive
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_listening_admin_integration import World, _put
from test_speaking_candidate_integration import _record, webm
from test_writing_candidate_integration import _drain, _post

from app.modules.speaking import voice

db_url = _admin.db_url
redis = _admin.redis
s3 = _admin.s3
world = _admin.world

pytestmark = pytest.mark.integration
A = "/admin/speaking"
S = "/speaking"


async def _published_config(w: World) -> dict[str, Any]:
    test_id = (await publish_productive(w, "speaking"))["test"]["id"]
    options = (await w.owner.get(f"{A}/tests")).json()
    assert test_id in {o["test_id"] for o in options}
    created = await w.owner.post(f"{A}/configs", {"test_id": test_id})
    assert created.status_code == 201, created.text
    c = created.json()
    assert c["status"] == "draft"
    assert c["body"]["part1_questions"] == [0, 1]  # defaults: every existing question, in order
    body = c["body"]
    body["part1_questions"] = [1, 0]  # reorder
    body["instructions"]["introduction"] = "Hello, I am {examiner}. Let's start."
    saved = await _put(w.owner, f"{A}/configs/{c['id']}", {"revision": c["revision"], "body": body})
    assert saved.status_code == 200, saved.text
    preview = (await w.owner.get(f"{A}/configs/{c['id']}/preview")).json()
    assert preview["issues"] == []
    kinds = [(s["role"], s["part_no"], s["kind"]) for s in preview["plan"]]
    assert kinds[0] == ("examiner", 1, "intro")
    assert ("examiner", 2, "cue_card") in kinds
    assert kinds[-1] == ("examiner", 3, "closing")
    assert preview["plan"][1]["text"] == "Do you like living there?"  # reordered
    assert len(preview["rules"]) == 10
    assert (await w.manager.post(f"{A}/configs/{c['id']}/publish")).status_code == 403
    pub = await w.owner.post(f"{A}/configs/{c['id']}/publish")
    assert pub.status_code == 200, pub.text
    return dict(pub.json())


async def test_admin_configuration_and_publish_protection(world: World) -> None:
    w = world
    profiles = (await w.owner.get(f"{A}/examiners")).json()
    assert [p["code"] for p in profiles][:3] == ["supportive", "standard", "challenging"]
    assert all(p["voice"] == {} for p in profiles)  # no voice is configured yet
    edited = await _put(
        w.owner,
        f"{A}/examiners/{profiles[0]['id']}",
        {
            **{
                k: profiles[0][k]
                for k in (
                    "name",
                    "title",
                    "personality",
                    "speaking_style",
                    "difficulty",
                    "avatar_tone",
                    "is_active",
                )
            },
            "accent": "British English (planned)",
        },
    )
    assert edited.status_code == 200
    assert edited.json()["accent"] == "British English (planned)"
    config = await _published_config(w)
    locked = await _put(
        w.owner,
        f"{A}/configs/{config['id']}",
        {"revision": config["revision"], "body": config["body"]},
    )
    assert locked.status_code == 409
    with pytest.raises(DBAPIError, match="content_version_immutable"):
        await w.sql(text("UPDATE examiner_configs SET config = '{}' WHERE status = 'published'"))
    bad = dict(config["body"])
    bad["part3_questions"] = [7]
    un = await w.owner.post(f"{A}/configs/{config['id']}/unpublish")
    assert un.json()["status"] == "unpublished"
    invalid = await _put(
        w.owner, f"{A}/configs/{config['id']}", {"revision": un.json()["revision"], "body": bad}
    )
    assert invalid.status_code == 422
    assert (await w.student.get(f"{A}/configs")).status_code == 403


async def test_guided_room_end_to_end_with_pending_evaluation(world: World) -> None:
    w = world
    config = await _published_config(w)
    examiners = (await w.student.get(f"{S}/examiners")).json()
    daniel = next(e for e in examiners if e["code"] == "standard")
    assert daniel["voice_configured"] is False
    tests = (await w.student.get(f"{S}/room-tests")).json()
    assert config["id"] in {t["config_id"] for t in tests}

    no_consent = await _post(
        w.student,
        f"{S}/rooms",
        {
            "examiner_id": daniel["id"],
            "config_id": config["id"],
            "voice_processing_consent": False,
            "audio_recording_consent": True,
        },
    )
    assert no_consent.status_code == 422
    created = await _post(
        w.student,
        f"{S}/rooms",
        {
            "examiner_id": daniel["id"],
            "config_id": config["id"],
            "voice_processing_consent": True,
            "audio_recording_consent": True,
        },
    )
    assert created.status_code == 201, created.text
    room = created.json()
    rid = room["id"]
    assert room["status"] == "created"
    assert room["room_code"].startswith("room-")
    assert room["transcript"] == []
    assert room["answers_total"] == 5  # 2 + cue card + 1 rounding + 1 Part 3
    assert (await w.reviewer.get(f"{S}/rooms/{rid}")).status_code == 404

    entered = (await _post(w.student, f"{S}/rooms/{rid}/enter")).json()
    assert entered["connection"] is None
    room = entered["room"]
    assert room["status"] == "live"
    assert room["voice"]["mode"] == "guided"
    assert [t["speaker"] for t in room["transcript"]] == ["examiner", "examiner"]
    assert room["transcript"][0]["text"] == "Hello, I am Daniel. Let's start."
    again = (await _post(w.student, f"{S}/rooms/{rid}/enter")).json()["room"]
    assert len(again["transcript"]) == 2  # entering twice adds nothing

    # The room never moves on without a verified recording of the current answer.
    early = await _post(w.student, f"{S}/rooms/{rid}/advance", {"step": room["current"]["step"]})
    assert early.status_code == 409
    while room["current"] is not None:
        cur = room["current"]
        done = await _record(w, rid, cur["part_no"], cur["question_no"], webm(cur["step"]))
        assert done.status_code == 200, done.text
        nxt = await _post(w.student, f"{S}/rooms/{rid}/advance", {"step": cur["step"]})
        assert nxt.status_code == 200, nxt.text
        dup = await _post(w.student, f"{S}/rooms/{rid}/advance", {"step": cur["step"]})
        assert dup.status_code == 200  # retried request: no duplicate line
        room = nxt.json()
        if cur["part_no"] == 2 and cur["question_no"] == 1:
            assert cur["cue_card"]["prompt"].startswith("Describe")
            assert cur["prep_seconds"] == 60
    assert room["status"] == "completed"
    assert room["completion_reason"] == "finished"
    seqs = [t["seq"] for t in room["transcript"]]
    assert seqs == sorted(seqs) == list(range(1, len(seqs) + 1))
    candidate = [t for t in room["transcript"] if t["speaker"] == "candidate"]
    assert len(candidate) == 5
    assert all(t["transcript_status"] == "pending" and t["text"] == "" for t in candidate)
    assert room["transcript"][-1]["kind"] == "closing"
    assert room["evaluation"]["status"] == "queued"
    await _drain(w)
    room = (await w.student.get(f"{S}/rooms/{rid}")).json()
    assert room["evaluation"]["status"] == "unavailable"  # no providers: pending, never a score
    assert room["evaluation"]["band_overall"] is None
    history = (await w.student.get(f"{S}/rooms")).json()
    assert history[0]["id"] == rid
    assert rid not in {s["id"] for s in (await w.student.get(f"{S}/sessions")).json()}


async def test_ending_early_and_live_event_boundary(world: World) -> None:
    w = world
    config = await _published_config(w)
    examiner = (await w.student.get(f"{S}/examiners")).json()[0]
    body = {
        "examiner_id": examiner["id"],
        "config_id": config["id"],
        "voice_processing_consent": True,
        "audio_recording_consent": True,
    }
    rid = (await _post(w.student, f"{S}/rooms", body)).json()["id"]
    await _post(w.student, f"{S}/rooms/{rid}/enter")
    ended = (await _post(w.student, f"{S}/rooms/{rid}/end")).json()
    assert ended["status"] == "completed"
    assert ended["completion_reason"] == "ended_by_candidate"
    assert ended["evaluation"] is None  # nothing recorded, nothing to evaluate

    # Live mode through a test-double voice adapter (no real provider).
    class FakeVoice:
        name = "fake-voice"
        ended: ClassVar[list[str]] = []

        async def create_session(self, room: voice.RoomContext) -> voice.VoiceConnection:
            assert room.plan[0]["kind"] == "intro"
            assert "Ask one question at a time." in room.instructions["rules"]
            return voice.VoiceConnection(
                "fake-voice",
                "wss://voice.invalid",
                "token",
                datetime.now(UTC) + timedelta(minutes=5),
            )

        async def end_session(self, room_code: str) -> None:
            self.ended.append(room_code)

    voice.register(FakeVoice())
    try:
        rid = (await _post(w.student, f"{S}/rooms", body)).json()["id"]
        entered = (await _post(w.student, f"{S}/rooms/{rid}/enter")).json()
        assert entered["connection"]["provider"] == "fake-voice"
        assert entered["room"]["voice"]["mode"] == "live"
        assert entered["room"]["transcript"] == []
        events = {
            "events": [
                {
                    "seq": 1,
                    "type": "transcript",
                    "speaker": "examiner",
                    "text": "Good morning.",
                    "part_no": 1,
                }
            ]
        }
        url = f"/api/v1/internal/speaking/rooms/{rid}/events"
        assert (await w.anonymous.client.post(url, json=events)).status_code == 404  # disabled
        original = w.app.state.settings
        w.app.state.settings = original.model_copy(
            update={"speaking_events_token": SecretStr("t" * 32)}
        )
        try:
            bad = await w.anonymous.client.post(
                url, json=events, headers={"X-Internal-Token": "wrong"}
            )
            assert bad.status_code == 404
            ok = await w.anonymous.client.post(
                url, json=events, headers={"X-Internal-Token": "t" * 32}
            )
            assert ok.status_code == 202, ok.text
            assert ok.json()["stored"] == 1
            dup = await w.anonymous.client.post(
                url, json=events, headers={"X-Internal-Token": "t" * 32}
            )
            assert dup.json()["stored"] == 0  # idempotent on seq
        finally:
            w.app.state.settings = original
        room = (await w.student.get(f"{S}/rooms/{rid}")).json()
        assert [t["text"] for t in room["transcript"]] == ["Good morning."]
        await _post(w.student, f"{S}/rooms/{rid}/end")
        assert FakeVoice.ended
    finally:
        voice.register(None)
    assert uuid.UUID(rid)
