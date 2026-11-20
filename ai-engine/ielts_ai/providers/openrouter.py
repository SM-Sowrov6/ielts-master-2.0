"""OpenRouter adapter (OpenAI-compatible Chat Completions API, https://openrouter.ai).

Used by the site assistant with OpenRouter's free models. Models are tried in the configured
order: when one is rate limited (429), overloaded (5xx), retired (404) or times out, the next one
is tried. If every model failed and at least one answered 429, `OpenRouterError.rate_limited` is
set so callers can tell the user to wait instead of reporting an outage.

The key is sent in the `Authorization` header and never logged. Only the messages built by the
caller are sent; this adapter adds nothing about the user.
"""

import time
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx
from pydantic import BaseModel

from ielts_ai.providers.base import LLMCapabilities, LLMRequest, LLMResponse

API = "https://openrouter.ai/api/v1/chat/completions"
RETRY_STATUSES = {404, 408, 429, 500, 502, 503, 504}
# Extra completion tokens allowed for hidden reasoning, so it cannot crowd out the answer.
REASONING_TOKENS = 2000


class OpenRouterError(RuntimeError):
    """No configured model returned a usable answer."""

    def __init__(self, message: str, *, rate_limited: bool = False) -> None:
        super().__init__(message)
        self.rate_limited = rate_limited


class OpenRouterLLM:
    name = "openrouter"
    capabilities = LLMCapabilities(structured_output=False, max_context_tokens=32_000)

    def __init__(
        self,
        api_key: str,
        models: Sequence[str],
        *,
        timeout_seconds: float = 20.0,
        app_url: str | None = None,
        app_title: str = "IELTS MASTER",
        transport: httpx.AsyncBaseTransport | None = None,
        api_url: str = API,
        reasoning: str = "off",
    ) -> None:
        unique = [m for i, m in enumerate(models) if m and m not in models[:i]]
        if not unique:
            raise ValueError("At least one OpenRouter model is required")
        self.models = unique
        self._key = api_key
        self._timeout = timeout_seconds
        self._transport = transport
        self._url = api_url
        self._reasoning = reasoning
        self._headers = {"Authorization": f"Bearer {api_key}", "X-Title": app_title}
        if app_url:
            self._headers["HTTP-Referer"] = app_url
        self.last_model = unique[0]

    @property
    def model(self) -> str:
        return self.last_model

    def _body(self, request: LLMRequest, model: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
        }
        if self._reasoning != "off":
            # Reasoning is used to think, never returned or stored ("exclude"). Only plain
            # content is kept in the conversation, so no reasoning_details are passed back.
            reasoning: dict[str, Any] = {"enabled": True, "exclude": True}
            if self._reasoning in ("low", "medium", "high"):
                reasoning["effort"] = self._reasoning
            body["reasoning"] = reasoning
            body["max_tokens"] = request.max_output_tokens + REASONING_TOKENS
        return body

    async def generate(self, request: LLMRequest) -> LLMResponse:
        last_error = "no model available"
        rate_limited = False
        # One overall deadline across fallbacks, so a slow chain cannot exceed the request budget.
        deadline = time.monotonic() + self._timeout
        async with httpx.AsyncClient(transport=self._transport) as client:
            for model in self.models:
                remaining = deadline - time.monotonic()
                if remaining <= 0.5:
                    last_error = "deadline exceeded"
                    break
                try:
                    r = await client.post(
                        self._url,
                        headers=self._headers,
                        json=self._body(request, model),
                        timeout=remaining,
                    )
                except httpx.TimeoutException:
                    last_error = f"{model}: timeout"
                    continue
                except httpx.HTTPError as exc:
                    last_error = f"{model}: {type(exc).__name__}"
                    continue
                if r.status_code == 429:
                    rate_limited = True
                if r.status_code in RETRY_STATUSES:
                    last_error = f"{model}: HTTP {r.status_code}"
                    continue
                if r.status_code != 200:
                    # 400/401/402/403: configuration problem; another model will not fix it.
                    raise OpenRouterError(f"{model}: HTTP {r.status_code}")
                try:
                    data = r.json()
                except ValueError:
                    last_error = f"{model}: invalid JSON"
                    continue
                if data.get("error"):
                    # OpenRouter can return 200 with an upstream error object.
                    code = (data["error"] or {}).get("code")
                    rate_limited = rate_limited or code == 429
                    last_error = f"{model}: upstream error {code}"
                    continue
                choices = data.get("choices") or []
                message = (choices[0].get("message") or {}) if choices else {}
                text = (message.get("content") or "").strip()
                if not text:
                    last_error = f"{model}: empty response"
                    continue
                usage = data.get("usage") or {}
                self.last_model = str(data.get("model") or model)
                return LLMResponse(
                    text=text,
                    model=self.last_model,
                    input_tokens=int(usage.get("prompt_tokens") or 0),
                    output_tokens=int(usage.get("completion_tokens") or 0),
                )
        raise OpenRouterError(last_error, rate_limited=rate_limited)

    async def generate_structured[T: BaseModel](self, request: LLMRequest, schema: type[T]) -> T:
        response = await self.generate(request)
        text = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        return schema.model_validate_json(text)

    def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        raise NotImplementedError("Streaming is not used yet.")
