"""Reading end to end against real PostgreSQL, Redis and MinIO: admin authoring (3 passages,
all Reading types) -> four-eyes publish -> candidate attempt -> scoring -> review.
Requires the same variables as test_listening_admin_integration.py."""

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from reading_fixtures import ANSWERS, READING_TYPES, reading_sections
from redis.asyncio import Redis
from sqlalchemy.engine import make_url
from test_identity_integration import ALEMBIC_INI
from test_listening_admin_integration import (
    API,
    World,
    _env,
    _put,
    _save_body,
    admin_setup,
    close_world,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def reading_db(test_database_url: str) -> str:
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["configure_logger"] = False
    cfg.attributes["database_url"] = test_database_url
    command.upgrade(cfg, "head")
    return test_database_url


@pytest.fixture
async def world(reading_db: str, test_redis_url: str) -> AsyncIterator[World]:
    redis_url = make_url(test_redis_url).set(database="15").render_as_string(hide_password=False)
    client = Redis.from_url(redis_url)
    await client.flushdb()
    await client.aclose()
    endpoint = _env("TEST_S3_ENDPOINT_URL")
    media = {
        "s3_endpoint_url": endpoint,
        "s3_public_endpoint_url": endpoint,
        "s3_access_key_id": _env("TEST_S3_ACCESS_KEY_ID"),
        "s3_secret_access_key": _env("TEST_S3_SECRET_ACCESS_KEY"),
        "s3_bucket": "ielts-media-test",
    }
    w, app = await admin_setup(reading_db, redis_url, media)
    yield w
    await close_world(w, app)


async def _post(b: Any, path: str, body: Any = None, **headers: str) -> Any:
    token = b.client.cookies.get("ielts_csrf") or await b.csrf()
    return await b.client.post(
        f"/api/v1{path}", json=body, headers={"X-CSRF-Token": token, **headers}
    )


async def _publish_reading(w: World) -> dict[str, Any]:
    created = await w.owner.post(
        f"{API}/reading/tests",
        {
            "edition_id": w.edition_id,
            "code": f"R-{uuid.uuid4().hex[:6]}",
            "title": "Synthetic Reading",
            "duration_seconds": 3600,
        },
    )
    assert created.status_code == 201, created.text
    doc = created.json()
    assert [s["section_no"] for s in doc["sections"]] == [1, 2, 3]
    saved = await _put(
        w.owner, f"{API}/versions/{doc['version']['id']}", _save_body(doc, reading_sections())
    )
    assert saved.status_code == 200, saved.text
    d = saved.json()["document"]
    assert not [i for i in saved.json()["issues"] if i["severity"] == "error"], saved.json()[
        "issues"
    ]
    assert {g["question_type"] for s in d["sections"] for g in s["groups"]} == READING_TYPES
    assert d["sections"][0]["passages"][0]["paragraphs"][1]["label"] == "B"
    first = d["sections"][0]["groups"][0]["questions"][0]
    assert first["explanation"]["evidence_paragraph_label"] == "A"
    vid = d["version"]["id"]
    assert (await w.owner.post(f"{API}/versions/{vid}/submit")).status_code == 200
    assert (
        await w.reviewer.post(f"{API}/versions/{vid}/review", {"decision": "approved"})
    ).status_code == 200
    published = await w.owner.post(f"{API}/versions/{vid}/publish")
    assert published.status_code == 200, published.text
    return dict(published.json())


async def test_reading_admin_rules_and_listing(world: World) -> None:
    w = world
    doc = (
        await w.owner.post(
            f"{API}/reading/tests",
            {
                "edition_id": w.edition_id,
                "code": "R-x" + uuid.uuid4().hex[:4],
                "title": "Draft reading",
            },
        )
    ).json()
    # Reading sections may not carry audio; the publish validator demands passages.
    bad = reading_sections()
    bad[0]["audio_asset_id"] = str(uuid.uuid4())
    r = await _put(w.owner, f"{API}/versions/{doc['version']['id']}", _save_body(doc, bad))
    assert r.status_code == 422
    assert any(i["code"] == "audio_not_allowed" for i in r.json()["issues"])
    empty = (await w.owner.get(f"{API}/versions/{doc['version']['id']}/validation")).json()
    assert "passage_missing" in {i["code"] for i in empty["issues"]}
    types = {t["code"] for t in (await w.owner.get(f"{API}/question-types?module=reading")).json()}
    assert types == READING_TYPES
    listed = (await w.owner.get(f"{API}/reading/tests?limit=100")).json()
    assert doc["test"]["id"] in {row["test_id"] for row in listed["items"]}
    listening = (await w.owner.get(f"{API}/listening/tests?limit=100")).json()
    assert doc["test"]["id"] not in {row["test_id"] for row in listening["items"]}
    assert (await w.student.get(f"{API}/reading/tests")).status_code == 403


async def test_reading_candidate_attempt_scoring_and_review(world: World) -> None:
    w = world
    pub = await _publish_reading(w)
    test_id = pub["test"]["id"]
    listed = await w.student.client.get("/api/v1/reading/tests")
    assert test_id in {t["test_id"] for t in listed.json()}
    detail = (await w.student.client.get(f"/api/v1/reading/tests/{test_id}")).json()
    exam = next(m for m in detail["modes"] if m["mode"] == "exam")
    assert exam["time_limit_seconds"] == 3600
    created = await _post(
        w.student,
        "/attempts",
        {"test_id": test_id, "mode": "exam", "module": "reading"},
        **{"Idempotency-Key": str(uuid.uuid4())},
    )
    assert created.status_code == 201, created.text
    attempt = created.json()["id"]
    assert created.json()["module"] == "reading"
    lease = (await _post(w.student, f"/attempts/{attempt}/start")).json()
    content = (await w.student.client.get(f"/api/v1/attempts/{attempt}/content")).json()
    raw = json.dumps(content)
    for secret in ("Synthetic explanation", "accepted", "harbour", "evidence"):
        assert secret not in raw, secret
    assert content["module"] == "reading"
    assert content["sections"][0]["passages"][0]["paragraphs"][0]["label"] == "A"
    tfng = content["sections"][0]["groups"][0]
    assert [o["label"] for o in tfng["options"]] == ["TRUE", "FALSE", "NOT GIVEN"]
    ids = {
        q["number_from"]: q["id"]
        for s in content["sections"]
        for g in s["groups"]
        for q in g["questions"]
    }
    answers = [
        {
            "question_id": ids[n],
            "response": ANSWERS[n] if n != 2 else {"choice": "TRUE"},
            "client_revision": 1,
        }
        for n in ids
    ]
    token = w.student.client.cookies.get("ielts_csrf")
    saved = await w.student.client.put(
        f"/api/v1/attempts/{attempt}/answers",
        json={"writer_epoch": lease["writer_epoch"], "answers": answers},
        headers={"X-CSRF-Token": token, "X-Writer-Token": lease["writer_token"]},
    )
    assert saved.status_code == 200, saved.text
    done = await _post(
        w.student,
        f"/attempts/{attempt}/submit",
        {"writer_epoch": lease["writer_epoch"]},
        **{"Idempotency-Key": str(uuid.uuid4()), "X-Writer-Token": lease["writer_token"]},
    )
    assert done.status_code == 200, done.text
    result = (await w.student.client.get(f"/api/v1/attempts/{attempt}/result")).json()
    assert (result["raw_score"], result["max_score"]) == (39, 40)  # Q2 answered wrongly
    assert result["band_available"] is False
    assert {s["section_no"] for s in result["sections"]} == {1, 2, 3}
    review = (await w.student.client.get(f"/api/v1/attempts/{attempt}/review")).json()
    q1 = next(i for i in review["items"] if i["number_from"] == 1)
    assert q1["evidence_paragraph"] == "A"
    assert q1["accepted"] == [["TRUE"]]
    history = (await w.student.client.get("/api/v1/attempts?module=reading")).json()["items"]
    assert [h["id"] for h in history] == [attempt]
    assert (await w.student.client.get("/api/v1/attempts?module=listening")).json()["items"] == []
