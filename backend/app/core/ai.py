"""AI provider resolution for evaluations (ADR-003: workflows live in `ielts_ai`).

Provider: Google Gemini (D-07 decided by the product owner on 2026-11-19), configured with
`GEMINI_API_KEY` / `GEMINI_MODEL`. Without a key `providers()` has no LLM and evaluations end
`unavailable`; scores are never invented. Tests install fakes with `use_providers`.
"""

from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import Settings
from ielts_ai.providers.base import LLMProvider, PronunciationAssessor, STTProvider
from ielts_ai.providers.gemini import GeminiLLM, GeminiSTT


@dataclass(frozen=True)
class Providers:
    llm: LLMProvider | None = None
    llm_model: str = ""
    stt: STTProvider | None = None
    pronunciation: PronunciationAssessor | None = None


_factory: Callable[[Settings], Providers] | None = None


def register(factory: Callable[[Settings], Providers] | None) -> None:
    """Install the provider factory (adapters, or test doubles). None removes it."""
    global _factory
    _factory = factory


def use_providers(providers: Providers | None) -> None:
    register((lambda _settings: providers) if providers is not None else None)


def configured(settings: Settings) -> Providers:
    """Providers from settings: Gemini for evaluation and transcription when a key is set.
    No pronunciation assessor is configured, so Pronunciation is reported as not assessed."""
    if settings.gemini_api_key is None:
        return Providers()
    key = settings.gemini_api_key.get_secret_value()
    return Providers(
        llm=GeminiLLM(key, settings.gemini_model),
        llm_model=settings.gemini_model,
        stt=GeminiSTT(key, settings.gemini_model),
    )


def providers(settings: Settings) -> Providers:
    return _factory(settings) if _factory is not None else configured(settings)
