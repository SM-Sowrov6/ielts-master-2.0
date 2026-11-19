"""Candidate Writing end to end against real PostgreSQL/Redis/MinIO: draft, revision-guarded
autosave, idempotent immutable submit, background AI evaluation through the real outbox worker.

The LLM is a test double (`FakeLLM`): no real provider is contacted. Without a provider the
evaluation must end `unavailable` with no bands; that path is tested first."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import test_listening_admin_integration as _admin
from productive_fixtures import ESSAY, publish_productive, publish_rubric
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_listening_admin_integration import API, World, _put

from app.core import ai
from app.core.email import MemoryEmailSender
from app.workers.outbox import Dispatcher
from ielts_ai.providers.base import LLMCapabilities, LLMRequest, LLMResponse

# Shared fixtures (pytest discovers them as module attributes).
db_url = _admin.db_url
redis = _admin.redis
s3 = _admin.s3
world = _admin.world

pytestmark = pytest.mark.integration
W = "/writing"


class FakeLLM:
    name = "fake-llm"
    capabilities = LLMCapabilities(structured_output=True, max_context_tokens=8000)

    def __init__(self, payload: dict[str, Any] | Exception) -> None:
        self.payload = payload
        self.calls: list[LLMRequest] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError

    async def generate_structured[T: BaseModel](self, request: LLMRequest, schema: type[T]) -> T:
        self.calls.append(request)
        if isinstance(self.payload, Exception):
            raise self.payload
        return schema.model_validate(self.payload)

    def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        raise NotImplementedError


GOOD: dict[str, Any] = {
    "criteria": [
        {
            "code": c,
            "band": b,
            "rationale": f"{c} rationale",
            "strengths": ["s"],
            "improvements": ["i"],
        }
        for c, b in (("TA", 7), ("CC", 6.5), ("LR", 6.5), ("GRA", 6))
    ],
    "feedback": [
        {
            "kind": "grammar",
            "excerpt": "move far more people",
            "suggestion": "carry",
            "explanation": "e",
        }
    ],
    "summary": "A clear, well-supported position.",
}


async def _post(b: Any, path: str, body: Any = None, **headers: str) -> httpx.Response:
    token = b.client.cookies.get("ielts_csrf") or await b.csrf()
    response: httpx.Response = await b.client.post(
        f"/api/v1{path}", json=body, headers={"X-CSRF-Token": token, **headers}
    )
    return response


async def _drain(w: World) -> None:
    dispatcher = Dispatcher(
        w.app.state.settings, w.app.state.db_session_factory, MemoryEmailSender()
    )
    while await dispatcher.process_batch():
        pass


async def _submitted(w: World, test_id: str, task_no: int = 2) -> dict[str, Any]:
    s = await _post(w.student, f"{W}/submissions", {"test_id": test_id, "task_no": task_no})
    assert s.status_code == 201, s.text
    sid = s.json()["id"]
    done = await _post(
        w.student,
        f"{W}/submissions/{sid}/submit",
        {"body": ESSAY, "client_revision": 1, "time_spent_seconds": 1200},
        **{"Idempotency-Key": str(uuid.uuid4())},
    )
    assert done.status_code == 200, done.text
    return dict(done.json())


async def test_drafts_autosave_submit_and_immutability(world: World) -> None:
    w = world
    pub = await publish_productive(w, "writing")
    test_id = pub["test"]["id"]
    listed = (await w.student.get(f"{W}/tests")).json()
    assert isinstance(listed, list), listed
    assert test_id in {t["test_id"] for t in listed}
    detail = (await w.student.get(f"{W}/tests/{test_id}")).json()
    assert [t["task_no"] for t in detail["tasks"]] == [1, 2]
    assert "model_answers" not in str(detail)  # never before submission

    first = await _post(w.student, f"{W}/submissions", {"test_id": test_id, "task_no": 2})
    assert first.status_code == 201
    sid = first.json()["id"]
    again = await _post(w.student, f"{W}/submissions", {"test_id": test_id, "task_no": 2})
    assert again.json()["id"] == sid  # one open draft per task
    assert first.json()["model_answers"] == []

    ok = await _put(
        w.student, f"{W}/submissions/{sid}", {"body": "Draft one", "client_revision": 2}
    )
    assert ok.status_code == 200
    assert ok.json()["word_count"] == 2
    stale = await _put(
        w.student, f"{W}/submissions/{sid}", {"body": "old tab", "client_revision": 1}
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_revision"
    # Someone else's draft does not exist for them.
    assert (await w.reviewer.get(f"{W}/submissions/{sid}")).status_code == 404

    key = str(uuid.uuid4())
    body = {"body": ESSAY, "client_revision": 3, "time_spent_seconds": 900}
    done = await _post(w.student, f"{W}/submissions/{sid}/submit", body, **{"Idempotency-Key": key})
    assert done.status_code == 200
    sub = done.json()
    assert sub["status"] == "submitted"
    assert sub["word_count"] == 100
    assert sub["evaluation"]["status"] == "queued"
    assert sub["model_answers"][0]["band"] == 8.0  # revealed after submission
    retried = await _post(
        w.student, f"{W}/submissions/{sid}/submit", body, **{"Idempotency-Key": key}
    )
    assert retried.status_code == 200  # same key: same result, no second evaluation
    other = await _post(
        w.student, f"{W}/submissions/{sid}/submit", body, **{"Idempotency-Key": str(uuid.uuid4())}
    )
    assert other.status_code == 409
    locked = await _put(w.student, f"{W}/submissions/{sid}", {"body": "edit", "client_revision": 9})
    assert locked.status_code == 409
    with pytest.raises(DBAPIError, match="submission_immutable"):
        await w.sql(
            text(
                "UPDATE writing_submissions SET body = 'x' WHERE id = CAST(:id AS uuid)"
            ).bindparams(id=sid)
        )
    count = (
        await w.sql(
            text(
                "SELECT count(*) FROM writing_evaluations WHERE submission_id = CAST(:id AS uuid)"
            ).bindparams(id=sid)
        )
    ).scalar()
    assert count == 1
    # A new draft can be started after submitting.
    fresh = await _post(w.student, f"{W}/submissions", {"test_id": test_id, "task_no": 2})
    assert fresh.json()["id"] != sid


async def test_evaluation_is_unavailable_without_provider_then_succeeds_with_one(
    world: World,
) -> None:
    w = world
    test_id = (await publish_productive(w, "writing"))["test"]["id"]
    ai.use_providers(ai.Providers())
    sub = await _submitted(w, test_id)
    await _drain(w)
    got = (await w.student.get(f"{W}/submissions/{sub['id']}")).json()["evaluation"]
    assert got["status"] == "unavailable"
    assert got["band_overall"] is None
    assert got["criteria"] == []
    assert got["retryable"] is True

    # Provider configured but no rubric published yet: still honest, still no score.
    fake = FakeLLM(GOOD)
    ai.use_providers(ai.Providers(llm=fake, llm_model="fake-1"))
    try:
        key = {"Idempotency-Key": str(uuid.uuid4())}
        assert (
            await _post(w.student, f"{W}/submissions/{sub['id']}/evaluations", None, **key)
        ).status_code == 202
        await _drain(w)
        got = (await w.student.get(f"{W}/submissions/{sub['id']}")).json()["evaluation"]
        if got["status"] == "unavailable":
            assert "rubric" in got["message"]
            await publish_rubric(w, "writing")
            key = {"Idempotency-Key": str(uuid.uuid4())}
            assert (
                await _post(w.student, f"{W}/submissions/{sub['id']}/evaluations", None, **key)
            ).status_code == 202
            await _drain(w)
            got = (await w.student.get(f"{W}/submissions/{sub['id']}")).json()["evaluation"]
        assert got["status"] == "succeeded", got
        assert got["band_overall"] == 6.5  # mean 6.5 computed by the platform
        assert [c["code"] for c in got["criteria"]] == ["TA", "CC", "LR", "GRA"]
        assert got["criteria"][0]["name"] == "Criterion TA"  # from the published rubric
        assert got["feedback"][0]["excerpt"] == "move far more people"
        assert got["provider"] == "fake-llm"
        assert got["retryable"] is False
        # The candidate text reached the model only inside the delimited data block.
        assert "<candidate_response>" in fake.calls[-1].messages[1].content
        no_retry = await _post(
            w.student,
            f"{W}/submissions/{sub['id']}/evaluations",
            None,
            **{"Idempotency-Key": str(uuid.uuid4())},
        )
        assert no_retry.status_code == 409
    finally:
        ai.use_providers(ai.Providers())


async def test_bad_provider_output_fails_after_retries_and_short_text_is_rejected(
    world: World,
) -> None:
    w = world
    test_id = (await publish_productive(w, "writing"))["test"]["id"]
    rubrics = (await w.owner.get(f"{API}/rubrics?module=writing")).json()
    if not any(r["status"] == "published" for r in rubrics):
        await publish_rubric(w, "writing")
    ai.use_providers(
        ai.Providers(
            llm=FakeLLM({"criteria": [GOOD["criteria"][0]], "summary": "x"}), llm_model="m"
        )
    )
    try:
        sub = await _submitted(w, test_id)
        await _drain(w)
        got = (await w.student.get(f"{W}/submissions/{sub['id']}")).json()["evaluation"]
        assert got["status"] == "failed"
        assert got["band_overall"] is None
        attempts = (
            await w.sql(
                text(
                    "SELECT attempt_count FROM writing_evaluations "
                    "WHERE submission_id = CAST(:id AS uuid)"
                ).bindparams(id=sub["id"])
            )
        ).scalar()
        assert attempts == 3

        s = await _post(w.student, f"{W}/submissions", {"test_id": test_id, "task_no": 1})
        short = await _post(
            w.student,
            f"{W}/submissions/{s.json()['id']}/submit",
            {"body": "Too short to assess.", "client_revision": 1},
            **{"Idempotency-Key": str(uuid.uuid4())},
        )
        assert short.status_code == 200
        await _drain(w)
        got = (await w.student.get(f"{W}/submissions/{s.json()['id']}")).json()["evaluation"]
        assert got["status"] == "rejected_input"
        assert got["band_overall"] is None
    finally:
        ai.use_providers(ai.Providers())
