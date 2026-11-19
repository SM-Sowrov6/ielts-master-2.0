"""Super Admin Writing/Speaking management and rubric versions against real PostgreSQL, Redis
and MinIO (same environment as test_listening_admin_integration.py). Synthetic content only."""

import uuid

import pytest
import test_listening_admin_integration as _admin
from listening_fixtures import png_bytes
from productive_fixtures import (
    productive_body,
    publish_productive,
    publish_rubric,
    rubric_criteria,
    speaking_parts,
    writing_tasks,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_listening_admin_integration import API, World, _put, _upload

# Shared fixtures (pytest discovers them as module attributes).
db_url = _admin.db_url
redis = _admin.redis
s3 = _admin.s3
world = _admin.world

pytestmark = pytest.mark.integration


async def test_writing_authoring_validation_model_answers_and_immutability(world: World) -> None:
    w = world
    created = await w.owner.post(
        f"{API}/writing/tests",
        {"edition_id": w.edition_id, "code": "W-" + uuid.uuid4().hex[:5], "title": "Synthetic W"},
    )
    assert created.status_code == 201, created.text
    doc = created.json()
    assert doc["module"] == "writing"
    assert doc["variant"] == "academic"
    assert [t["task_no"] for t in doc["writing_tasks"]] == [1, 2]
    vid = doc["version"]["id"]
    codes = {
        i["code"] for i in (await w.owner.get(f"{API}/versions/{vid}/validation")).json()["issues"]
    }
    assert {"writing_prompt_missing", "writing_visual_missing"} <= codes

    # Task 2 never carries a visual; the request fails as a whole and saves nothing.
    bad = writing_tasks(None)
    bad[1]["image_asset_id"] = str(uuid.uuid4())
    r = await _put(
        w.owner, f"{API}/versions/{vid}/productive", productive_body(doc, writing_tasks=bad)
    )
    assert r.status_code == 422
    assert any(i["code"] == "image_not_allowed" for i in r.json()["issues"])

    image = await _upload(w, doc["test"]["id"], png_bytes(), kind="image", mime="image/png")
    assert image.status_code == 200, image.text
    saved = await _put(
        w.owner,
        f"{API}/versions/{vid}/productive",
        productive_body(doc, writing_tasks=writing_tasks(image.json()["id"])),
    )
    assert saved.status_code == 200, saved.text
    assert not [i for i in saved.json()["issues"] if i["severity"] == "error"]
    task2 = saved.json()["document"]["writing_tasks"][1]
    assert task2["prompt_text"].startswith("Some people think")
    assert task2["model_answers"][0]["band"] == 8.0

    # Four-eyes, then the published model answers and tasks are immutable in the database.
    assert (await w.owner.post(f"{API}/versions/{vid}/submit")).status_code == 200
    assert (
        await w.owner.post(f"{API}/versions/{vid}/review", {"decision": "approved"})
    ).status_code == 403
    assert (
        await w.reviewer.post(f"{API}/versions/{vid}/review", {"decision": "approved"})
    ).status_code == 200
    assert (await w.owner.post(f"{API}/versions/{vid}/publish")).status_code == 200
    with pytest.raises(DBAPIError, match="content_version_immutable"):
        await w.sql(text("UPDATE sample_answers SET body = 'changed'"))
    with pytest.raises(DBAPIError, match="content_version_immutable"):
        await w.sql(text("UPDATE writing_tasks SET min_words = 10"))
    preview = (await w.owner.get(f"{API}/versions/{vid}/preview")).json()
    assert preview["writing_tasks"][0]["model_answers"]

    # A new revision deep-copies tasks and model answers into an editable draft.
    rev = await w.owner.post(f"{API}/tests/{doc['test']['id']}/revisions")
    assert rev.status_code == 201
    assert rev.json()["writing_tasks"][1]["model_answers"][0]["body"].startswith("Many cities")


async def test_speaking_parts_cue_card_rules_and_listing(world: World) -> None:
    w = world
    doc = (
        await w.owner.post(
            f"{API}/speaking/tests",
            {
                "edition_id": w.edition_id,
                "code": "S-" + uuid.uuid4().hex[:5],
                "title": "Synthetic S",
            },
        )
    ).json()
    assert [p["part_no"] for p in doc["speaking_parts"]] == [1, 2, 3]
    vid = doc["version"]["id"]
    codes = {
        i["code"] for i in (await w.owner.get(f"{API}/versions/{vid}/validation")).json()["issues"]
    }
    assert {"cue_card_missing", "speaking_topic_missing"} <= codes
    bad = speaking_parts()
    bad[0]["cue_card"] = {"prompt": "Not here"}
    r = await _put(
        w.owner, f"{API}/versions/{vid}/productive", productive_body(doc, speaking_parts=bad)
    )
    assert r.status_code == 422
    assert any(i["code"] == "cue_card_not_allowed" for i in r.json()["issues"])
    wrong = await _put(
        w.owner,
        f"{API}/versions/{vid}/productive",
        productive_body(doc, writing_tasks=writing_tasks(None)),
    )
    assert wrong.status_code == 422
    published = await publish_productive(w, "speaking")
    assert published["speaking_parts"][1]["cue_card"]["points"][0] == "what it is"
    listing = (await w.owner.get(f"{API}/speaking/tests?status=published")).json()
    assert published["version"]["id"] in {r["version_id"] for r in listing["items"]}
    overview = (await w.owner.get(f"{API}/speaking/overview")).json()
    assert overview["published"] >= 1
    # Students and anonymous visitors never reach the admin API.
    assert (await w.student.get(f"{API}/speaking/tests")).status_code == 403
    assert (await w.anonymous.get(f"{API}/rubrics?module=writing")).status_code == 401


async def test_rubric_versions_four_eyes_and_immutability(world: World) -> None:
    w = world
    r = (await w.owner.post(f"{API}/rubrics", {"module": "writing"})).json()
    assert [c["code"] for c in r["criteria"]] == ["TA", "CC", "LR", "GRA"]
    assert r["criteria"][0]["bands"] == []  # no descriptor text is shipped
    assert (await w.owner.post(f"{API}/rubrics", {"module": "writing"})).status_code == 409
    refused = await w.owner.post(f"{API}/rubrics/{r['id']}/submit")
    assert refused.status_code == 422
    wrong = rubric_criteria("speaking")
    bad = await _put(
        w.owner,
        f"{API}/rubrics/{r['id']}",
        {"revision": r["revision"], "title": "x", "criteria": wrong},
    )
    assert bad.status_code == 422
    await _put(
        w.owner,
        f"{API}/rubrics/{r['id']}",
        {"revision": r["revision"], "title": "x", "criteria": rubric_criteria("writing")},
    )
    assert (await w.owner.post(f"{API}/rubrics/{r['id']}/submit")).status_code == 200
    own = await w.owner.post(f"{API}/rubrics/{r['id']}/review", {"decision": "approved"})
    assert own.status_code == 403
    assert (await w.owner.post(f"{API}/rubrics/{r['id']}/publish")).status_code == 409
    assert (
        await w.reviewer.post(f"{API}/rubrics/{r['id']}/review", {"decision": "approved"})
    ).status_code == 200
    assert (await w.manager.post(f"{API}/rubrics/{r['id']}/publish")).status_code == 403
    first = (await w.owner.post(f"{API}/rubrics/{r['id']}/publish")).json()
    assert first["status"] == "published"
    with pytest.raises(DBAPIError, match="content_version_immutable"):
        await w.sql(text("UPDATE rubric_versions SET criteria = '[]' WHERE status = 'published'"))
    second = await publish_rubric(w, "writing")
    assert second["version_no"] == first["version_no"] + 1
    statuses = {
        x["id"]: x["status"] for x in (await w.owner.get(f"{API}/rubrics?module=writing")).json()
    }
    assert statuses[first["id"]] == "archived"
    assert statuses[second["id"]] == "published"
