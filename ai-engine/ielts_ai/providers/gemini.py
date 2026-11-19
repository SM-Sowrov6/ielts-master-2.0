"""Google Gemini adapters (Generative Language REST API, API key from Google AI Studio).

- `GeminiLLM`: `generate` / `generate_structured` (JSON mode, Pydantic-validated, one repair
  attempt with the validation error). Streaming is not used by any feature yet.
- `GeminiSTT`: speech-to-text by sending the recording inline and asking for a verbatim transcript.

Models are tried in order: the configured model first, then fallbacks, when a model is retired
(404) or temporarily overloaded (429/503). The key is sent in the `x-goog-api-key` header and
never logged.
"""

import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from ielts_ai.providers.base import LLMCapabilities, LLMRequest, LLMResponse

API = "https://generativelanguage.googleapis.com/v1beta/models"
FALLBACK_MODELS = ("gemini-3.5-flash", "gemini-3.8-flash", "gemini-flash-latest")
RETRY_STATUSES = {404, 429, 500, 503}


class GeminiError(RuntimeError):
    """The provider did not return a usable answer (after trying every model)."""


def _models(primary: str, fallbacks: Sequence[str]) -> list[str]:
    out: list[str] = []
    for m in (primary, *fallbacks):
        if m and m not in out:
            out.append(m)
    return out


def _sniff_audio(audio: bytes) -> str:
    if audio.startswith(b"\x1a\x45\xdf\xa3"):
        return "audio/webm"
    if audio.startswith(b"OggS"):
        return "audio/ogg"
    if audio[4:8] == b"ftyp":
        return "audio/mp4"
    if audio.startswith(b"RIFF") and audio[8:12] == b"WAVE":
        return "audio/wav"
    if audio.startswith(b"ID3") or audio[:2] == b"\xff\xfb":
        return "audio/mp3"
    return "application/octet-stream"


class _Client:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        fallbacks: Sequence[str] = FALLBACK_MODELS,
        timeout_seconds: float = 180.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._key = api_key
        self.models = _models(model, fallbacks)
        self._timeout = timeout_seconds
        self._transport = transport
        self.last_model = model

    async def call(self, body: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """POST generateContent; returns (text, usage). Tries the models in order."""
        last_error = "no model available"
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            for model in self.models:
                try:
                    r = await client.post(
                        f"{API}/{model}:generateContent",
                        headers={"x-goog-api-key": self._key},
                        json=body,
                    )
                except httpx.TimeoutException:
                    last_error = f"{model}: timeout"
                    continue
                if r.status_code in RETRY_STATUSES:
                    last_error = f"{model}: HTTP {r.status_code}"
                    continue
                if r.status_code != 200:
                    raise GeminiError(f"{model}: HTTP {r.status_code}")
                data = r.json()
                candidates = data.get("candidates") or []
                parts = (candidates[0].get("content") or {}).get("parts") if candidates else None
                texts = [p["text"] for p in parts or [] if "text" in p and not p.get("thought")]
                if not texts:
                    last_error = f"{model}: empty response"
                    continue
                self.last_model = model
                return "".join(texts), data.get("usageMetadata") or {}
        raise GeminiError(last_error)


class GeminiLLM:
    name = "gemini"
    capabilities = LLMCapabilities(
        structured_output=True, json_schema_strict=False, max_context_tokens=1_000_000
    )

    def __init__(self, api_key: str, model: str, **kwargs: Any) -> None:
        self._client = _Client(api_key, model, **kwargs)

    @property
    def model(self) -> str:
        return self._client.last_model

    def _body(
        self, request: LLMRequest, *, json_mode: bool, extra: str | None = None
    ) -> dict[str, Any]:
        system = "\n\n".join(m.content for m in request.messages if m.role == "system")
        contents = [
            {"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]}
            for m in request.messages
            if m.role != "system"
        ]
        if extra:
            contents.append({"role": "user", "parts": [{"text": extra}]})
        config: dict[str, Any] = {
            "temperature": request.temperature,
            "maxOutputTokens": max(request.max_output_tokens, 8192),
        }
        if json_mode:
            config["responseMimeType"] = "application/json"
        body: dict[str, Any] = {"contents": contents, "generationConfig": config}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        return body

    async def generate(self, request: LLMRequest) -> LLMResponse:
        text, usage = await self._client.call(self._body(request, json_mode=False))
        return LLMResponse(
            text=text,
            model=self._client.last_model,
            input_tokens=int(usage.get("promptTokenCount", 0)),
            output_tokens=int(usage.get("candidatesTokenCount", 0)),
        )

    async def generate_structured[T: BaseModel](self, request: LLMRequest, schema: type[T]) -> T:
        text, _ = await self._client.call(self._body(request, json_mode=True))
        try:
            return schema.model_validate_json(text)
        except ValidationError as first:
            # One repair attempt: show the model its own output and the validation errors.
            repair = (
                "Your previous answer did not match the required JSON schema. Errors: "
                + json.dumps(first.errors(include_url=False, include_context=False), default=str)[
                    :4000
                ]
                + "\nYour previous answer was:\n"
                + text[:8000]
                + "\nReturn only the corrected JSON object."
            )
            fixed, _ = await self._client.call(self._body(request, json_mode=True, extra=repair))
            return schema.model_validate_json(fixed)

    def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        raise NotImplementedError("Streaming is not used yet.")


class GeminiSTT:
    """Verbatim transcription of a recorded answer (no correction of the candidate's errors)."""

    name = "gemini-stt"

    def __init__(self, api_key: str, model: str, **kwargs: Any) -> None:
        self._client = _Client(api_key, model, **kwargs)

    async def transcribe(self, audio: bytes, *, language: str, correlation_id: str) -> str:
        import base64

        body = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                f"Transcribe this {language} speech recording verbatim. Keep the "
                                "speaker's own words, grammar mistakes, repetitions and fillers "
                                "(um, uh). Do not correct, summarise or add anything. If nothing "
                                "intelligible is said, return an empty string. Return only the "
                                "transcript text."
                            )
                        },
                        {
                            "inlineData": {
                                "mimeType": _sniff_audio(audio),
                                "data": base64.b64encode(audio).decode("ascii"),
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 8192},
        }
        text, _ = await self._client.call(body)
        return text.strip()
