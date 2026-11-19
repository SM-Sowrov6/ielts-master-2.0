"""Provider interface boundaries (docs/AI_ENGINE_ARCHITECTURE.md §3). Adapters arrive in Phase 8."""

from ielts_ai.providers.base import (
    EmbeddingProvider,
    LLMCapabilities,
    LLMMessage,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    Operation,
    PronunciationAssessor,
    RealtimeVoiceProvider,
    STTProvider,
    TTSProvider,
    UsageEvent,
    UsageSink,
)

__all__ = [
    "EmbeddingProvider",
    "LLMCapabilities",
    "LLMMessage",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "Operation",
    "PronunciationAssessor",
    "RealtimeVoiceProvider",
    "STTProvider",
    "TTSProvider",
    "UsageEvent",
    "UsageSink",
]
