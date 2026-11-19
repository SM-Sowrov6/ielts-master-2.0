"""Super Admin Listening management against real PostgreSQL, Redis and MinIO (S3 API).

Requires TEST_DATABASE_ADMIN_URL, TEST_REDIS_URL, TEST_S3_ENDPOINT_URL, TEST_S3_ACCESS_KEY_ID
and TEST_S3_SECRET_ACCESS_KEY. Media goes to a separate `ielts-media-test` bucket.
All content is synthetic (tests/listening_fixtures.py).
"""

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from listening_fixtures import LISTENING_TYPES, listening_sections, png_bytes, sha256, wav_bytes
from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from test_identity_integration import ALEMBIC_INI, Browser, _register_and_verify, _settings

from app.core.email import MemoryEmailSender
from app.main import create_app
from app.modules.audit.models import AuditLog
from app.modules.content import api as content_api
from app.modules.content.models import MediaAsset, Question, TestVersion
from app.modules.identity.passwords import PasswordService
from app.modules.identity.provisioning import create_staff_account
from app.workers.outbox import Dispatcher

pytestmark = pytest.mark.integration

PASSWORD = "synthetic staff passphrase 5521"
HASHER = PasswordService(memory_kib=1024, iterations=1, concurrency=1)
API = "/admin/content"


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        if os.environ.get("REQUIRE_INTEGRATION_TESTS") == "1":
            pytest.fail(f"{name} must be set when REQUIRE_INTEGRATION_TESTS=1")
        pytest.skip(f"integration test: set {name} to run")
    return value


@pytest.fixture
def s3() -> dict[str, str]:
    endpoint = _env("TEST_S3_ENDPOINT_URL")
    return {
        "s3_endpoint_url": endpoint,
        "s3_public_endpoint_url": endpoint,
        "s3_access_key_id": _env("TEST_S3_ACCESS_KEY_ID"),
        "s3_secret_access_key": _env("TEST_S3_SECRET_ACCESS_KEY"),
        "s3_bucket": "ielts-media-test",
    }


@pytest.fixture
def db_url(test_database_url: str) -> str:
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["configure_logger"] = False
    cfg.attributes["database_url"] = test_database_url
    command.upgrade(cfg, "head")
    return test_database_url


@pytest.fixture
async def redis(test_redis_url: str) -> str:
    url = make_url(test_redis_url).set(database="15").render_as_string(hide_password=False)
    client = Redis.from_url(url)
    await client.flushdb()
    await client.aclose()
    return url


@dataclass
class World:
    app: Any
    owner: Browser  # super admin (author)
    reviewer: Browser  # second staff account (four-eyes)
    manager: Browser  # content_manager: edit, no publish
    student: Browser
    anonymous: Browser
    edition_id: str

    async def sql(self, statement: Any) -> Any:
        async with self.app.state.db_session_factory() as db, db.begin():
            return await db.execute(statement)


async def _staff(app: Any, role: str) -> Browser:
    email = f"{role}-{uuid.uuid4().hex[:8]}@example.test"
    async with app.state.db_session_factory() as db, db.begin():
        await create_staff_account(
            db, HASHER, email=email, full_name=f"Synthetic {role}", password=PASSWORD, role=role
        )
    browser = Browser(app, f"192.0.2.{uuid.uuid4().int % 250}")
    response = await browser.post("/auth/login", {"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return browser


async def _put(browser: Browser, path: str, body: dict[str, Any]) -> httpx.Response:
    token = browser.client.cookies.get("ielts_csrf") or await browser.csrf()
    return await browser.client.put(f"/api/v1{path}", json=body, headers={"X-CSRF-Token": token})


async def _delete(browser: Browser, path: str) -> httpx.Response:
    token = browser.client.cookies.get("ielts_csrf") or await browser.csrf()
    return await browser.client.delete(f"/api/v1{path}", headers={"X-CSRF-Token": token})


async def admin_setup(db_url: str, redis_url: str, s3: dict[str, str]) -> tuple[World, Any]:
    """App + staff accounts + an original-licence collection (shared with the candidate suite)."""
    settings = _settings(db_url, redis_url, **s3)
    app = create_app(settings)
    owner = await _staff(app, "super_admin")
    licence = await owner.post(f"{API}/licences", {"licensor": "Synthetic in-house team (test)"})
    assert licence.status_code == 201, licence.text
    book = await owner.post(
        f"{API}/books",
        {
            "license_id": licence.json()["id"],
            "slug": f"synthetic-listening-{uuid.uuid4().hex[:8]}",
            "title": "Synthetic Listening Collection (test data)",
        },
    )
    assert book.status_code == 201, book.text
    edition = await owner.post(
        f"{API}/books/{book.json()['id']}/editions", {"label": "Test edition"}
    )
    assert edition.status_code == 201, edition.text
    student_env = _StudentEnv(app, settings)
    student = await student_env.student()
    world = World(
        app=app,
        owner=owner,
        reviewer=await _staff(app, "reviewer"),
        manager=await _staff(app, "content_manager"),
        student=student,
        anonymous=Browser(app, "203.0.113.77"),
        edition_id=edition.json()["id"],
    )
    return world, app


async def close_world(world: World, app: Any) -> None:
    for b in (world.owner, world.reviewer, world.manager, world.student, world.anonymous):
        await b.close()
    await app.state.db_engine.dispose()
    await app.state.redis.aclose()


@pytest.fixture
async def world(db_url: str, redis: str, s3: dict[str, str]) -> AsyncIterator[World]:
    w, app = await admin_setup(db_url, redis, s3)
    yield w
    await close_world(w, app)


class _StudentEnv:
    """Registers and verifies a real student through the public API and the outbox."""

    def __init__(self, app: Any, settings: Any) -> None:
        self.app = app
        self.settings = settings
        self.outbox = MemoryEmailSender()
        self.dispatcher = Dispatcher(settings, app.state.db_session_factory, self.outbox)

    def browser(self, ip: str = "198.51.100.9") -> Browser:
        return Browser(self.app, ip)

    async def deliver(self) -> list[Any]:
        before = len(self.outbox.sent)
        while await self.dispatcher.process_batch():
            pass
        return self.outbox.sent[before:]

    async def student(self) -> Browser:
        async with self.app.state.db_session_factory() as db, db.begin():
            await db.execute(text("DELETE FROM outbox_messages"))
        email = await _register_and_verify(self)  # type: ignore[arg-type]
        browser = Browser(self.app, "198.51.100.200")
        response = await browser.post(
            "/auth/login", {"email": email, "password": "correct horse battery staple 42"}
        )
        assert response.status_code == 200, response.text
        return browser


# --------------------------------------------------------------------------------- helpers
async def _create(w: World, code: str | None = None, **extra: Any) -> dict[str, Any]:
    body = {
        "edition_id": w.edition_id,
        "code": code or f"L-{uuid.uuid4().hex[:6]}",
        "title": extra.pop("title", "Synthetic Listening Test"),
        "difficulty": extra.pop("difficulty", "medium"),
        "duration_seconds": 1800,
        "tags": ["synthetic"],
        "admin_notes": "Internal synthetic note",
        **extra,
    }
    response = await w.owner.post(f"{API}/listening/tests", body)
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _upload(
    w: World,
    test_id: str,
    data: bytes,
    *,
    kind: str = "audio",
    mime: str = "audio/wav",
    declared: bytes | None = None,
    browser: Browser | None = None,
) -> httpx.Response:
    """Full browser flow: ask for a presigned URL, PUT to MinIO, then complete."""
    declared = declared if declared is not None else data
    b = browser or w.owner
    ticket = await b.post(
        f"{API}/media",
        {
            "test_id": test_id,
            "kind": kind,
            "filename": f"synthetic.{mime.split('/')[1]}",
            "mime_type": mime,
            "size_bytes": len(declared),
            "sha256": sha256(declared),
        },
    )
    if ticket.status_code != 201:
        return ticket
    t = ticket.json()
    async with httpx.AsyncClient() as raw:
        put = await raw.put(t["upload_url"], content=data, headers=t["headers"])
    assert put.status_code == 200, put.text
    return await b.post(f"{API}/media/{t['asset']['id']}/complete")


async def _audio(w: World, test_id: str, seed: int) -> str:
    response = await _upload(w, test_id, wav_bytes(seed))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ready"
    return str(response.json()["id"])


def _save_body(doc: dict[str, Any], sections: list[dict[str, Any]], **over: Any) -> dict[str, Any]:
    v = doc["version"]
    return {
        "revision": v["revision"],
        "title": doc["test"]["title"],
        "description": v["description"],
        "difficulty": v["difficulty"],
        "tags": v["tags"],
        "duration_seconds": doc["duration_seconds"],
        "admin_notes": doc["test"]["admin_notes"],
        "change_note": v["change_note"],
        "sections": sections,
        **over,
    }


async def _full_draft(w: World, **create: Any) -> dict[str, Any]:
    doc = await _create(w, **create)
    test_id = doc["test"]["id"]
    audio = [await _audio(w, test_id, n) for n in range(4)]
    image = await _upload(w, test_id, png_bytes(), kind="image", mime="image/png")
    assert image.status_code == 200, image.text
    saved = await _put(
        w.owner,
        f"{API}/versions/{doc['version']['id']}",
        _save_body(doc, listening_sections(audio, image.json()["id"])),
    )
    assert saved.status_code == 200, saved.text
    return dict(saved.json())


async def _published(w: World) -> dict[str, Any]:
    saved = await _full_draft(w)
    vid = saved["document"]["version"]["id"]
    assert (await w.owner.post(f"{API}/versions/{vid}/submit")).status_code == 200
    approved = await w.reviewer.post(f"{API}/versions/{vid}/review", {"decision": "approved"})
    assert approved.status_code == 200, approved.text
    published = await w.owner.post(f"{API}/versions/{vid}/publish")
    assert published.status_code == 200, published.text
    return dict(published.json())


# --------------------------------------------------------------------------------- access
async def test_access_control_follows_existing_permissions(world: World) -> None:
    w = world
    doc = await _create(w)
    vid = doc["version"]["id"]
    reads = [
        f"{API}/listening/overview",
        f"{API}/listening/tests",
        f"{API}/versions/{vid}",
    ]
    for path in reads:
        assert (await w.anonymous.get(path)).status_code == 401, path
        denied = await w.student.get(path)
        assert denied.status_code == 403, path
        assert "sections" not in denied.text
        assert (await w.reviewer.get(path)).status_code == 200, path  # reviewers can read
    create = {"edition_id": w.edition_id, "code": "NOPE", "title": "x"}
    assert (await w.student.post(f"{API}/listening/tests", create)).status_code == 403
    assert (await w.reviewer.post(f"{API}/listening/tests", create)).status_code == 403  # no edit
    assert (await w.reviewer.post(f"{API}/licences", {"licensor": "x"})).status_code == 403
    media = {
        "test_id": doc["test"]["id"],
        "kind": "audio",
        "filename": "a.wav",
        "mime_type": "audio/wav",
        "size_bytes": 10,
        "sha256": "0" * 64,
    }
    assert (await w.student.post(f"{API}/media", media)).status_code == 403
    assert (await w.reviewer.post(f"{API}/media", media)).status_code == 403
    # CSRF applies to every admin mutation.
    raw = await w.owner.client.post(f"/api/v1{API}/listening/tests", json=create)
    assert raw.status_code == 403
    assert raw.json()["code"] == "csrf_failed"


# --------------------------------------------------------------------------------- create/edit
async def test_create_and_edit_a_draft_with_all_listening_question_types(world: World) -> None:
    w = world
    doc = await _create(w, title="Synthetic Create Test")
    assert doc["version"]["status"] == "draft"
    assert [s["section_no"] for s in doc["sections"]] == [1, 2, 3, 4]
    assert all(not s["groups"] for s in doc["sections"])
    assert doc["test"]["admin_notes"] == "Internal synthetic note"
    saved = await _full_draft(w)
    d = saved["document"]
    types = {g["question_type"] for s in d["sections"] for g in s["groups"]}
    assert types == LISTENING_TYPES
    assert not [i for i in saved["issues"] if i["severity"] == "error"], saved["issues"]
    numbers = sorted(
        n
        for s in d["sections"]
        for g in s["groups"]
        for q in g["questions"]
        for n in range(q["number_from"], (q["number_to"] or q["number_from"]) + 1)
    )
    assert numbers == list(range(1, 41))
    assert d["sections"][0]["context"] == "A synthetic everyday conversation."
    # Accepted alternatives round-trip as authored key notation.
    first = d["sections"][0]["groups"][0]["questions"][0]
    assert first["answers"][0]["value"] == "(the) library"
    assert first["lineage_id"]

    # Editing keeps question identity (lineage) and enforces optimistic concurrency.
    sections = d["sections"]
    sections[0]["title"] = "Synthetic part 1 (edited)"
    vid = d["version"]["id"]
    again = await _put(w.owner, f"{API}/versions/{vid}", _save_body(d, sections))
    assert again.status_code == 200, again.text
    assert (
        again.json()["document"]["sections"][0]["groups"][0]["questions"][0]["lineage_id"]
        == (first["lineage_id"])
    )
    stale = await _put(w.owner, f"{API}/versions/{vid}", _save_body(d, sections))
    assert stale.status_code == 409
    assert stale.json()["code"] == "content_draft_conflict"


async def test_question_validation_errors_have_locations_and_save_nothing(world: World) -> None:
    w = world
    saved = await _full_draft(w)
    d = saved["document"]
    vid = d["version"]["id"]

    async def attempt(mutate: Any) -> dict[str, Any]:
        sections = listening_sections([s["audio_asset_id"] for s in d["sections"]])
        mutate(sections)
        r = await _put(w.owner, f"{API}/versions/{vid}", _save_body(d, sections))
        assert r.status_code == 422, r.text
        body = dict(r.json())
        assert body["code"] == "content_validation_failed"
        return body

    def bad_key(s: list[dict[str, Any]]) -> None:
        s[0]["groups"][1]["questions"][0]["answers"] = [{"value": "Z"}]

    body = await attempt(bad_key)
    issue = next(i for i in body["issues"] if i["code"] == "key_not_an_option")
    assert "section 1 > group 2 (mcq_single) > Q6" in issue["location"]

    def reading_type(s: list[dict[str, Any]]) -> None:
        s[0]["groups"][1]["question_type"] = "tfng"
        for q in s[0]["groups"][1]["questions"]:
            q.pop("options")
            q["answers"] = [{"value": "TRUE"}]

    assert any(
        i["code"] == "question_type_not_in_module" for i in (await attempt(reading_type))["issues"]
    )

    def duplicate_number(s: list[dict[str, Any]]) -> None:
        s[3]["groups"][1]["questions"][0]["number_from"] = 31

    assert any(
        i["code"] == "question_numbers_duplicate"
        for i in (await attempt(duplicate_number))["issues"]
    )

    def over_limit(s: list[dict[str, Any]]) -> None:
        s[2]["groups"][0]["questions"][0]["answers"] = [{"value": "three whole words"}]

    assert any(i["code"] == "key_exceeds_word_limit" for i in (await attempt(over_limit))["issues"])

    def audio_as_image(s: list[dict[str, Any]]) -> None:
        s[1]["groups"][0]["image_asset_id"] = s[0]["audio_asset_id"]

    assert any(
        i["code"] == "asset_kind_mismatch" for i in (await attempt(audio_as_image))["issues"]
    )
    # Nothing was written by the rejected saves.
    current = (await w.owner.get(f"{API}/versions/{vid}")).json()
    assert current["version"]["revision"] == d["version"]["revision"]
    assert current["sections"][0]["groups"][1]["questions"][0]["answers"][0]["value"] == "B"


async def test_question_and_group_ordering_is_preserved(world: World) -> None:
    w = world
    saved = await _full_draft(w)
    d = saved["document"]
    sections = d["sections"]
    sections[1]["groups"].reverse()  # reorder groups inside section 2
    r = await _put(w.owner, f"{API}/versions/{d['version']['id']}", _save_body(d, sections))
    assert r.status_code == 200, r.text
    order = [g["question_type"] for g in r.json()["document"]["sections"][1]["groups"]]
    assert order == ["matching_features", "mcq_multi", "plan_labelling", "map_labelling"]
    preview = (await w.owner.get(f"{API}/versions/{d['version']['id']}/preview")).json()
    assert [g["question_type"] for g in preview["sections"][1]["groups"]] == order


# --------------------------------------------------------------------------------- media
async def test_audio_upload_is_verified_and_stored_in_object_storage(world: World) -> None:
    w = world
    doc = await _create(w)
    test_id = doc["test"]["id"]
    data = wav_bytes(7)
    ok = await _upload(w, test_id, data)
    assert ok.status_code == 200, ok.text
    asset_id = ok.json()["id"]
    row = (await w.sql(select(MediaAsset).where(MediaAsset.id == uuid.UUID(asset_id)))).scalar_one()
    assert row.status == "ready"
    assert row.checksum_sha256 == sha256(data)
    assert row.storage_key.startswith("uploads/audio/")
    assert row.original_filename == "synthetic.wav"
    # Playback URL serves the stored bytes (short-lived presigned GET).
    url = (await w.owner.get(f"{API}/media/{asset_id}/url")).json()["url"]
    async with httpx.AsyncClient() as raw:
        fetched = await raw.get(url)
    assert fetched.status_code == 200
    assert fetched.content == data
    assert (await w.student.get(f"{API}/media/{asset_id}/url")).status_code == 403
    # Completing twice is idempotent.
    assert (await w.owner.post(f"{API}/media/{asset_id}/complete")).status_code == 200


async def test_invalid_uploads_are_rejected_and_never_marked_ready(world: World) -> None:
    w = world
    test_id = (await _create(w))["test"]["id"]
    fake = await _upload(w, test_id, b"<html>not audio</html>" * 50, mime="audio/mpeg")
    assert fake.status_code == 422
    assert fake.json()["code"] == "media_rejected"
    tampered = await _upload(w, test_id, wav_bytes(1), declared=wav_bytes(2))
    assert tampered.status_code == 422
    failed = (await w.sql(select(func.count()).where(MediaAsset.status == "failed"))).scalar_one()
    assert failed >= 2
    for body in (
        {"mime_type": "video/mp4"},  # not an allowed type
        {"size_bytes": 10**12},  # over the limit
        {"sha256": "x" * 64},  # not a checksum
    ):
        payload = {
            "test_id": test_id,
            "kind": "audio",
            "filename": "a.wav",
            "mime_type": "audio/wav",
            "size_bytes": 100,
            "sha256": "a" * 64,
            **body,
        }
        r = await w.owner.post(f"{API}/media", payload)
        assert r.status_code == 422, (body, r.text)
    # Completing before the file reached storage is refused, and nothing becomes ready.
    ticket = await w.owner.post(
        f"{API}/media",
        {
            "test_id": test_id,
            "kind": "audio",
            "filename": "a.wav",
            "mime_type": "audio/wav",
            "size_bytes": 100,
            "sha256": "a" * 64,
        },
    )
    early = await w.owner.post(f"{API}/media/{ticket.json()['asset']['id']}/complete")
    assert early.status_code == 409
    assert early.json()["code"] == "media_invalid_state"


async def test_audio_replacement_uses_a_new_immutable_asset(world: World) -> None:
    w = world
    saved = await _full_draft(w)
    d = saved["document"]
    old = d["sections"][0]["audio_asset_id"]
    new = await _audio(w, d["test"]["id"], 99)
    sections = d["sections"]
    sections[0]["audio_asset_id"] = new
    r = await _put(w.owner, f"{API}/versions/{d['version']['id']}", _save_body(d, sections))
    assert r.status_code == 200, r.text
    assert r.json()["document"]["sections"][0]["audio_asset_id"] == new
    still = (
        await w.sql(select(MediaAsset.status).where(MediaAsset.id == uuid.UUID(old)))
    ).scalar_one()
    assert still == "ready"


async def test_uploads_fail_honestly_without_storage(
    db_url: str, redis: str, s3: dict[str, str]
) -> None:
    for overrides, code in (
        ({"s3_endpoint_url": None}, "media_storage_unavailable"),
        ({"media_uploads_enabled": False}, "media_uploads_disabled"),
    ):
        app = create_app(_settings(db_url, redis, **{**s3, **overrides}))
        owner = await _staff(app, "super_admin")
        r = await owner.post(
            f"{API}/media",
            {
                "test_id": str(uuid.uuid4()),
                "kind": "audio",
                "filename": "a.wav",
                "mime_type": "audio/wav",
                "size_bytes": 100,
                "sha256": "a" * 64,
            },
        )
        assert r.status_code == 503, r.text
        assert r.json()["code"] == code
        await owner.close()
        await app.state.db_engine.dispose()
        await app.state.redis.aclose()


# --------------------------------------------------------------------------------- workflow
async def test_validation_submit_review_publish_and_four_eyes(world: World) -> None:
    w = world
    doc = await _create(w)
    vid = doc["version"]["id"]
    empty = (await w.owner.get(f"{API}/versions/{vid}/validation")).json()
    assert not empty["ok"]
    codes = {i["code"] for i in empty["issues"]}
    assert {"listening_audio_missing", "questions_missing", "question_count"} <= codes
    refused = await w.owner.post(f"{API}/versions/{vid}/submit")
    assert refused.status_code == 422
    assert refused.json()["issues"]

    saved = await _full_draft(w)
    vid = saved["document"]["version"]["id"]
    assert (await w.owner.get(f"{API}/versions/{vid}/validation")).json()["ok"]
    sub = await w.owner.post(f"{API}/versions/{vid}/submit")
    assert sub.status_code == 200
    assert sub.json()["version"]["status"] == "in_review"
    # The author cannot review their own version, and publishing needs an approval.
    own = await w.owner.post(f"{API}/versions/{vid}/review", {"decision": "approved"})
    assert own.status_code == 403
    assert own.json()["code"] == "content_self_review_forbidden"
    early = await w.owner.post(f"{API}/versions/{vid}/publish")
    assert early.status_code == 409
    assert early.json()["code"] == "content_review_required"
    # In review, the draft is locked.
    locked = await _put(w.owner, f"{API}/versions/{vid}", _save_body(saved["document"], []))
    assert locked.status_code == 409
    # A reviewer approves; a content manager still cannot publish.
    approve = await w.reviewer.post(
        f"{API}/versions/{vid}/review", {"decision": "approved", "comment": "Looks fine"}
    )
    assert approve.status_code == 200
    assert approve.json()["version"]["approved"] is True
    assert approve.json()["version"]["reviews"][0]["reviewer_name"] == "Synthetic reviewer"
    assert (await w.manager.post(f"{API}/versions/{vid}/publish")).status_code == 403
    listed = (await w.owner.get(f"{API}/listening/tests?status=approved")).json()
    assert vid in {r["version_id"] for r in listed["items"]}
    published = await w.owner.post(f"{API}/versions/{vid}/publish")
    assert published.status_code == 200
    assert published.json()["version"]["status"] == "published"
    assert published.json()["test"]["live_version_id"] == vid

    actions = set(
        (
            await w.sql(
                select(AuditLog.action).where(
                    AuditLog.entity_id.in_(
                        [uuid.UUID(vid), uuid.UUID(saved["document"]["test"]["id"])]
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    assert {
        "content.test.create",
        "content.test_version.save_draft",
        "content.test_version.submit",
        "content.test_version.review",
        "content.test_version.publish",
    } <= actions
    media_actions = set(
        (await w.sql(select(AuditLog.action).where(AuditLog.entity_type == "media_asset")))
        .scalars()
        .all()
    )
    assert {
        "content.media.upload_started",
        "content.media.uploaded",
        "content.media.rejected",
    } & media_actions


async def test_changes_requested_returns_the_version_to_draft(world: World) -> None:
    w = world
    saved = await _full_draft(w)
    vid = saved["document"]["version"]["id"]
    await w.owner.post(f"{API}/versions/{vid}/submit")
    back = await w.reviewer.post(
        f"{API}/versions/{vid}/review",
        {"decision": "changes_requested", "comment": "Fix part 2"},
    )
    assert back.status_code == 200
    assert back.json()["version"]["status"] == "draft"
    assert back.json()["version"]["reviews"][0]["comment"] == "Fix part 2"


async def test_published_content_is_immutable_and_revisions_deep_copy(world: World) -> None:
    w = world
    pub = await _published(w)
    vid, test_id = pub["version"]["id"], pub["test"]["id"]
    edit = await _put(w.owner, f"{API}/versions/{vid}", _save_body(pub, pub["sections"]))
    assert edit.status_code == 409
    assert edit.json()["code"] == "content_invalid_state"
    assert (await _delete(w.owner, f"{API}/versions/{vid}")).status_code == 409

    revision = await w.owner.post(f"{API}/tests/{test_id}/revisions")
    assert revision.status_code == 201, revision.text
    draft = revision.json()
    assert draft["version"]["version_no"] == 2
    assert draft["version"]["status"] == "draft"
    assert draft["test"]["live_version_id"] == vid  # v1 stays live while v2 is edited
    v1 = {q["lineage_id"] for s in pub["sections"] for g in s["groups"] for q in g["questions"]}
    v2 = {q["lineage_id"] for s in draft["sections"] for g in s["groups"] for q in g["questions"]}
    assert v1 == v2
    again = await w.owner.post(f"{API}/tests/{test_id}/revisions")
    assert again.status_code == 409  # one open draft per test
    sections = draft["sections"]
    sections[3]["instructions"] = "Synthetic revised instructions."
    saved = await _put(
        w.owner, f"{API}/versions/{draft['version']['id']}", _save_body(draft, sections)
    )
    assert saved.status_code == 200, saved.text
    v2_id = draft["version"]["id"]
    await w.owner.post(f"{API}/versions/{v2_id}/submit")
    await w.reviewer.post(f"{API}/versions/{v2_id}/review", {"decision": "approved"})
    assert (await w.owner.post(f"{API}/versions/{v2_id}/publish")).status_code == 200
    v1_status = (
        await w.sql(select(TestVersion.status).where(TestVersion.id == uuid.UUID(vid)))
    ).scalar_one()
    assert v1_status == "archived"

    archived = await w.owner.post(f"{API}/versions/{v2_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["version"]["status"] == "archived"
    assert archived.json()["test"]["live_version_id"] is None
    row = next(
        r
        for r in (await w.owner.get(f"{API}/listening/tests?status=archived&limit=100")).json()[
            "items"
        ]
        if r["test_id"] == test_id
    )
    assert row["live_version_id"] is None


async def test_duplicate_and_delete_draft(world: World) -> None:
    w = world
    pub = await _published(w)
    code = f"COPY-{uuid.uuid4().hex[:5]}"
    copy = await w.owner.post(
        f"{API}/versions/{pub['version']['id']}/duplicate",
        {"code": code, "title": "Synthetic copy"},
    )
    assert copy.status_code == 201, copy.text
    c = copy.json()
    assert c["test"]["id"] != pub["test"]["id"]
    assert c["version"]["status"] == "draft"
    assert c["version"]["version_no"] == 1
    original = {
        q["lineage_id"] for s in pub["sections"] for g in s["groups"] for q in g["questions"]
    }
    copied = {q["lineage_id"] for s in c["sections"] for g in s["groups"] for q in g["questions"]}
    assert len(copied) == len(original) == 39  # same structure (39 question rows) ...
    assert not original & copied  # ... but a new question history
    clash = await w.owner.post(
        f"{API}/versions/{pub['version']['id']}/duplicate", {"code": code, "title": "x"}
    )
    assert clash.status_code == 409
    gone = await _delete(w.owner, f"{API}/versions/{c['version']['id']}")
    assert gone.status_code == 204
    assert (await w.owner.get(f"{API}/versions/{c['version']['id']}")).status_code == 404


# --------------------------------------------------------------------------------- listing
async def test_overview_search_filters_and_pagination(world: World) -> None:
    w = world
    tag = uuid.uuid4().hex[:6]
    await _create(w, title=f"Alpha {tag}", difficulty="easy")
    await _create(w, title=f"Beta {tag}", difficulty="hard")
    await _create(w, title=f"Gamma {tag}", difficulty="hard")
    page = (await w.owner.get(f"{API}/listening/tests?search={tag}&limit=2")).json()
    assert page["total"] == 3
    assert len(page["items"]) == 2
    rest = (await w.owner.get(f"{API}/listening/tests?search={tag}&limit=2&offset=2")).json()
    assert len(rest["items"]) == 1
    titles = {r["title"] for r in page["items"] + rest["items"]}
    assert titles == {f"Alpha {tag}", f"Beta {tag}", f"Gamma {tag}"}
    hard = (await w.owner.get(f"{API}/listening/tests?search={tag}&difficulty=hard")).json()
    assert {r["title"] for r in hard["items"]} == {f"Beta {tag}", f"Gamma {tag}"}
    drafts = (await w.owner.get(f"{API}/listening/tests?search={tag}&status=published")).json()
    assert drafts["total"] == 0
    row = page["items"][0]
    assert row["sections"] == 4
    assert row["questions"] == 0
    assert row["created_by_name"] == "Synthetic super_admin"
    like = (
        await w.owner.get(f"{API}/listening/tests?search=%25")
    ).json()  # literal %, not a wildcard
    assert like["total"] == 0
    overview = (await w.owner.get(f"{API}/listening/overview")).json()
    listed = (await w.owner.get(f"{API}/listening/tests?limit=100")).json()["total"]
    assert overview["total"] == listed
    assert overview["total"] == sum(
        overview[k] for k in ("draft", "in_review", "approved", "published", "archived")
    )
    assert (await w.owner.get(f"{API}/listening/tests?limit=1000")).status_code == 422


# --------------------------------------------------------------------------------- preview/keys
async def test_admin_preview_shows_answers_but_student_views_never_do(world: World) -> None:
    w = world
    pub = await _published(w)
    vid = pub["version"]["id"]
    preview = (await w.owner.get(f"{API}/versions/{vid}/preview")).json()
    first_group = preview["sections"][0]["groups"][0]
    assert first_group["answers"][0]["accepted"][0][0] == "the library"
    assert preview["sections"][0]["audio_asset_id"]
    assert (await w.student.get(f"{API}/versions/{vid}/preview")).status_code == 403
    # Previews are not attempts: nothing is scored or stored.
    async with w.app.state.db_session_factory() as db, db.begin():
        view = await content_api.get_student_view(db, uuid.UUID(vid))
    flat = repr(view)
    for secret in ("the library", "accepted", "answers", "explanation", "Internal synthetic note"):
        assert secret not in flat, secret
    assert view["modules"][0]["sections"][0]["has_audio"] is True
    questions = (await w.sql(select(func.count()).select_from(Question))).scalar_one()
    assert questions > 0
