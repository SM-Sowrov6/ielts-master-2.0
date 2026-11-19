"""Synthetic Writing/Speaking content and rubric text written for tests (not IELTS material)."""

import uuid
from typing import Any

from test_listening_admin_integration import API, World, _put

TASK1 = (
    "The chart shows how many visitors three invented city museums received each year "
    "between 2010 and 2020. Summarise the information by selecting and reporting the main "
    "features, and make comparisons where relevant."
)
TASK2 = (
    "Some people think cities should spend more on public transport than on new roads. "
    "To what extent do you agree or disagree? Give reasons for your answer."
)
ESSAY = (
    "Many cities face a choice between building new roads and investing in public transport. "
    "In my view, public transport deserves the larger share of the budget, although roads "
    "still matter. Firstly, buses and trains move far more people per lane than private cars, "
    "so they reduce congestion for everyone. Secondly, cleaner transport lowers air pollution, "
    "which improves public health and saves money in the long term. On the other hand, some "
    "rural areas depend on roads because no rail line reaches them. Even so, I believe a "
    "balanced plan that favours public transport is the wisest option for growing cities."
)


def writing_tasks(image_id: str | None) -> list[dict[str, Any]]:
    return [
        {
            "task_no": 1,
            "prompt_text": TASK1,
            "image_asset_id": image_id,
            "min_words": 150,
            "key_features": ["overall trend", "highest and lowest museum"],
            "model_answers": [{"band": 7.5, "body": "The chart compares visitor numbers..."}],
        },
        {
            "task_no": 2,
            "prompt_text": TASK2,
            "image_asset_id": None,
            "min_words": 250,
            "key_features": [],
            "model_answers": [{"band": 8, "body": ESSAY, "author_note": "In-house sample."}],
        },
    ]


def speaking_parts() -> list[dict[str, Any]]:
    return [
        {
            "part_no": 1,
            "topic": "Hometown",
            "questions": [
                {"text": "Where is your hometown?"},
                {"text": "Do you like living there?"},
            ],
            "model_answers": [],
        },
        {
            "part_no": 2,
            "topic": "A useful object",
            "cue_card": {
                "prompt": "Describe an object you use every day.",
                "points": ["what it is", "when you got it", "how you use it"],
                "closing": "and explain why it is useful to you.",
            },
            "questions": [{"text": "Would you replace it?", "is_follow_up": True}],
            "model_answers": [{"band": 7, "body": "I'd like to talk about my bicycle..."}],
        },
        {
            "part_no": 3,
            "topic": "Technology and daily life",
            "questions": [{"text": "How has technology changed daily routines?"}],
            "model_answers": [],
        },
    ]


def productive_body(doc: dict[str, Any], **over: Any) -> dict[str, Any]:
    body = {
        "revision": doc["version"]["revision"],
        "title": doc["test"]["title"],
        "description": None,
        "difficulty": "medium",
        "tags": [],
        "duration_seconds": doc["duration_seconds"],
        "admin_notes": None,
        "change_note": None,
        "writing_tasks": [],
        "speaking_parts": [],
    }
    body.update(over)
    return body


def rubric_criteria(module: str) -> list[dict[str, Any]]:
    codes = ["TA", "CC", "LR", "GRA"] if module == "writing" else ["FC", "LR", "GRA", "PR"]
    return [
        {
            "code": c,
            "name": f"Criterion {c}",
            "description": f"Platform wording for {c} (synthetic).",
            "bands": [
                {"band": b, "descriptor": f"Synthetic descriptor {c} band {b}."}
                for b in (9, 7, 5, 3)
            ],
        }
        for c in codes
    ]


async def publish_rubric(w: World, module: str) -> dict[str, Any]:
    created = await w.owner.post(f"{API}/rubrics", {"module": module})
    assert created.status_code == 201, created.text
    r = created.json()
    saved = await _put(
        w.owner,
        f"{API}/rubrics/{r['id']}",
        {
            "revision": r["revision"],
            "title": f"{module} rubric",
            "criteria": rubric_criteria(module),
        },
    )
    assert saved.status_code == 200, saved.text
    assert (await w.owner.post(f"{API}/rubrics/{r['id']}/submit")).status_code == 200
    ok = await w.reviewer.post(f"{API}/rubrics/{r['id']}/review", {"decision": "approved"})
    assert ok.status_code == 200, ok.text
    pub = await w.owner.post(f"{API}/rubrics/{r['id']}/publish")
    assert pub.status_code == 200, pub.text
    return dict(pub.json())


async def publish_productive(
    w: World, module: str, *, variant: str = "general", image_id: str | None = None
) -> dict[str, Any]:
    created = await w.owner.post(
        f"{API}/{module}/tests",
        {
            "edition_id": w.edition_id,
            "code": f"{module[0].upper()}-{uuid.uuid4().hex[:6]}",
            "title": f"Synthetic {module} test",
            "variant": variant if module == "writing" else None,
        },
    )
    assert created.status_code == 201, created.text
    doc = created.json()
    over = (
        {"writing_tasks": writing_tasks(image_id)}
        if module == "writing"
        else {"speaking_parts": speaking_parts()}
    )
    saved = await _put(
        w.owner, f"{API}/versions/{doc['version']['id']}/productive", productive_body(doc, **over)
    )
    assert saved.status_code == 200, saved.text
    errors = [i for i in saved.json()["issues"] if i["severity"] == "error"]
    assert not errors, errors
    vid = doc["version"]["id"]
    assert (await w.owner.post(f"{API}/versions/{vid}/submit")).status_code == 200
    ok = await w.reviewer.post(f"{API}/versions/{vid}/review", {"decision": "approved"})
    assert ok.status_code == 200
    pub = await w.owner.post(f"{API}/versions/{vid}/publish")
    assert pub.status_code == 200, pub.text
    return dict(pub.json())
