"""OpenRouter adapter and the assistant workflow against mocked transports (no network)."""

import json

import httpx
import pytest

from ielts_ai.graphs import assistant
from ielts_ai.providers.base import LLMMessage, LLMRequest
from ielts_ai.providers.openrouter import OpenRouterError, OpenRouterLLM

REQ = LLMRequest(
    feature="t",
    correlation_id="c",
    messages=(LLMMessage(role="system", content="sys"), LLMMessage(role="user", content="hi")),
)


def ok(text: str, model: str = "b:free") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": model,
            "choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2},
        },
    )


async def test_falls_back_on_rate_limit_and_sends_headers() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body["model"])
        assert request.headers["authorization"] == "Bearer k"
        assert request.headers["http-referer"] == "https://app.example"
        assert body["messages"][0] == {"role": "system", "content": "sys"}
        if body["model"] == "a:free":
            return httpx.Response(429, json={"error": {"message": "rate limited"}})
        return ok(" hello ")

    llm = OpenRouterLLM(
        "k",
        ["a:free", "b:free", "a:free"],
        app_url="https://app.example",
        transport=httpx.MockTransport(handler),
    )
    out = await llm.generate(REQ)
    assert out.text == "hello"
    assert (out.model, out.input_tokens, out.output_tokens) == ("b:free", 4, 2)
    assert seen == ["a:free", "b:free"]


async def test_all_rate_limited_sets_flag() -> None:
    llm = OpenRouterLLM(
        "k",
        ["a:free", "b:free"],
        transport=httpx.MockTransport(lambda r: httpx.Response(429)),
    )
    with pytest.raises(OpenRouterError) as info:
        await llm.generate(REQ)
    assert info.value.rate_limited is True


async def test_upstream_error_in_200_body_and_empty_answers_fall_through() -> None:
    replies = iter(
        [
            httpx.Response(200, json={"error": {"code": 429, "message": "upstream"}}),
            ok(""),
            httpx.Response(503),
        ]
    )
    llm = OpenRouterLLM(
        "k", ["a:free", "b:free", "c:free"], transport=httpx.MockTransport(lambda r: next(replies))
    )
    with pytest.raises(OpenRouterError) as info:
        await llm.generate(REQ)
    assert info.value.rate_limited is True


async def test_auth_error_stops_immediately_without_leaking_key() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    llm = OpenRouterLLM("secret-key", ["a:free", "b:free"], transport=httpx.MockTransport(handler))
    with pytest.raises(OpenRouterError) as info:
        await llm.generate(REQ)
    assert calls == 1
    assert info.value.rate_limited is False
    assert "secret-key" not in str(info.value)


async def test_timeout_falls_back() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if json.loads(request.content)["model"] == "a:free":
            raise httpx.ReadTimeout("slow")
        return ok("fine")

    llm = OpenRouterLLM("k", ["a:free", "b:free"], transport=httpx.MockTransport(handler))
    assert (await llm.generate(REQ)).text == "fine"


def test_requires_a_model() -> None:
    with pytest.raises(ValueError, match="At least one"):
        OpenRouterLLM("k", [])


def test_assistant_messages_are_trimmed_and_start_with_user() -> None:
    history = [assistant.ChatTurn(role="assistant", content="Welcome")]
    for i in range(20):
        history.append(assistant.ChatTurn(role="user", content=f"q{i}" + "x" * 3000))
        history.append(assistant.ChatTurn(role="assistant", content=f"a{i}"))
    history.append(assistant.ChatTurn(role="user", content="last‮question"))
    context = assistant.AssistantContext(site_pages="- /writing (Writing): w", first_name="Ana")
    messages, version = assistant.build_messages(history, context)
    assert version == "1.0.0"
    assert messages[0].role == "system"
    assert "first name is Ana" in messages[0].content
    turns = messages[1:]
    assert len(turns) <= assistant.MAX_TURNS
    assert turns[0].role == "user"
    assert all(len(m.content) <= assistant.MAX_MESSAGE_CHARS for m in turns)
    assert turns[-1].content == "lastquestion"  # bidi override removed


async def test_reasoning_is_requested_hidden_and_given_token_headroom() -> None:
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return ok("answer")

    transport = httpx.MockTransport(handler)
    await OpenRouterLLM("k", ["a:free"], reasoning="on", transport=transport).generate(REQ)
    await OpenRouterLLM("k", ["a:free"], reasoning="low", transport=transport).generate(REQ)
    await OpenRouterLLM("k", ["a:free"], transport=transport).generate(REQ)
    assert bodies[0]["reasoning"] == {"enabled": True, "exclude": True}
    assert bodies[0]["max_tokens"] == REQ.max_output_tokens + 2000
    assert bodies[1]["reasoning"] == {"enabled": True, "exclude": True, "effort": "low"}
    assert "reasoning" not in bodies[2]
    assert bodies[2]["max_tokens"] == REQ.max_output_tokens
