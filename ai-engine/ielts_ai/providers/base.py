"""Provider protocols. Provisional shapes — refined with the first real adapters in Phase 8.

Capabilities are declared by each provider and never assumed (docs/AI_ENGINE_ARCHITECTURE.md §3).
"""

from collections.abc import AsyncIterator
from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class Operation(StrEnum):
    LLM = "llm"
    STT = "stt"
    TTS = "tts"
    EMBEDDING = "embed"
    PRONUNCIATION = "pronunciation"
    REALTIME_VOICE = "realtime_voice"


class UsageEvent(BaseModel):
    """Emitted for every provider call; the backend persists it to `ai_requests`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    feature: str
    provider: str
    model: str
    operation: Operation
    correlation_id: str
    succeeded: bool
    latency_ms: int = Field(ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    audio_ms: int = Field(default=0, ge=0)
    cost_micro_usd: int | None = Field(default=None, ge=0)


class UsageSink(Protocol):
    def __call__(self, event: UsageEvent) -> None: ...


class LLMCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    structured_output: bool = False
    json_schema_strict: bool = False
    tool_calling: bool = False
    streaming: bool = False
    vision: bool = False
    max_context_tokens: int = Field(gt=0)


class LLMMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str


class LLMRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    feature: str
    correlation_id: str
    messages: tuple[LLMMessage, ...]
    max_output_tokens: int = Field(default=1024, gt=0)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)


class LLMResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    capabilities: LLMCapabilities

    async def generate(self, request: LLMRequest) -> LLMResponse: ...

    async def generate_structured[T: BaseModel](
        self, request: LLMRequest, schema: type[T]
    ) -> T: ...

    def stream(self, request: LLMRequest) -> AsyncIterator[str]: ...


@runtime_checkable
class STTProvider(Protocol):
    name: str

    async def transcribe(self, audio: bytes, *, language: str, correlation_id: str) -> str: ...


@runtime_checkable
class TTSProvider(Protocol):
    name: str

    def synthesize(self, text: str, *, voice: str, correlation_id: str) -> AsyncIterator[bytes]: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str
    dimensions: int

    async def embed(self, texts: list[str], *, correlation_id: str) -> list[list[float]]: ...


@runtime_checkable
class PronunciationAssessor(Protocol):
    """Audio-based pronunciation scoring (ADR-011) — never inferred from transcripts."""

    name: str

    async def assess(
        self, audio: bytes, *, reference_text: str | None, correlation_id: str
    ) -> dict[str, float]: ...


@runtime_checkable
class RealtimeVoiceProvider(Protocol):
    """Optional speech-to-speech session (ADR-015); must still emit transcripts and turn events."""

    name: str

    async def open_session(self, *, instructions: str, correlation_id: str) -> str: ...

    async def close_session(self, session_id: str) -> None: ...
