"""Gemini adapter against a mocked HTTP transport (no network)."""

import json

import httpx
import pytest
from pydantic import BaseModel

from ielts_ai.providers.base import LLMMessage, LLMRequest
from ielts_ai.providers.gemini import GeminiError, GeminiLLM, GeminiSTT


class Out(BaseModel):
    ok: bool


def reply(text: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "candidates": [
                {"content": {"parts": [{"text": "thinking", "thought": True}, {"text": text}]}}
            ],
            "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 2},
        },
    )


REQ = LLMRequest(
    feature="t",
    correlation_id="c",
    messages=(LLMMessage(role="system", content="sys"), LLMMessage(role="user", content="hi")),
)


async def test_falls_back_on_overload_and_sends_key_in_header() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        assert request.headers["x-goog-api-key"] == "k"
        assert "key=" not in str(request.url)
        body = json.loads(request.content)
        assert body["systemInstruction"]["parts"][0]["text"] == "sys"
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        if "gemini-a" in request.url.path:
            return httpx.Response(503, json={"error": {"message": "busy"}})
        return reply('{"ok": true}')

    llm = GeminiLLM(
        "k", "gemini-a", fallbacks=("gemini-b",), transport=httpx.MockTransport(handler)
    )
    assert (await llm.generate_structured(REQ, Out)).ok is True
    assert llm.model == "gemini-b"
    assert [p.split("/")[-1] for p in seen] == [
        "gemini-a:generateContent",
        "gemini-b:generateContent",
    ]


async def test_one_repair_attempt_then_validation_error() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return reply('{"wrong": 1}' if calls == 1 else '{"ok": false}')

    llm = GeminiLLM("k", "m", fallbacks=(), transport=httpx.MockTransport(handler))
    assert (await llm.generate_structured(REQ, Out)).ok is False
    assert calls == 2


async def test_all_models_failing_raises_and_stt_sends_audio() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={})

    with pytest.raises(GeminiError):
        await GeminiLLM("k", "m", fallbacks=("n",), transport=httpx.MockTransport(down)).generate(
            REQ
        )

    def stt(request: httpx.Request) -> httpx.Response:
        part = json.loads(request.content)["contents"][0]["parts"][1]["inlineData"]
        assert part["mimeType"] == "audio/webm"
        return reply("  I usually walk to work.  ")

    text = await GeminiSTT("k", "m", transport=httpx.MockTransport(stt)).transcribe(
        b"\x1a\x45\xdf\xa3" + b"0" * 32, language="English", correlation_id="c"
    )
    assert text == "I usually walk to work."
