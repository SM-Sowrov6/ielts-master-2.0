"""AI provider resolution for evaluations (ADR-003: workflows live in `ielts_ai`).

Provider: Google Gemini (D-07 decided by the product owner on 2026-11-19), configured with
`GEMINI_API_KEY` / `GEMINI_MODEL`. Without a key `providers()` has no LLM and evaluations end
`unavailable`; scores are never invented. Tests install fakes with `use_providers`.

Site assistant: OpenRouter free models (`OPENROUTER_API_KEY` / `ASSISTANT_MODELS`), falling back
to the Gemini key when no OpenRouter key is set. `assistant` is None when neither is configured
or `ASSISTANT_ENABLED=false`.
"""

from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import Settings
from ielts_ai.providers.base import LLMProvider, PronunciationAssessor, STTProvider
from ielts_ai.providers.gemini import GeminiLLM, GeminiSTT
from ielts_ai.providers.openrouter import OpenRouterLLM


@dataclass(frozen=True)
class Providers:
    llm: LLMProvider | None = None
    llm_model: str = ""
    stt: STTProvider | None = None
    pronunciation: PronunciationAssessor | None = None
    assistant: LLMProvider | None = None


_factory: Callable[[Settings], Providers] | None = None


def register(factory: Callable[[Settings], Providers] | None) -> None:
    """Install the provider factory (adapters, or test doubles). None removes it."""
    global _factory
    _factory = factory


def use_providers(providers: Providers | None) -> None:
    register((lambda _settings: providers) if providers is not None else None)


def _assistant(settings: Settings) -> LLMProvider | None:
    if not settings.assistant_enabled:
        return None
    if settings.openrouter_api_key is not None and settings.assistant_model_list:
        return OpenRouterLLM(
            settings.openrouter_api_key.get_secret_value(),
            settings.assistant_model_list,
            timeout_seconds=settings.assistant_timeout_seconds,
            app_url=settings.app_origin,
            reasoning=settings.assistant_reasoning,
        )
    if settings.gemini_api_key is not None:
        return GeminiLLM(
            settings.gemini_api_key.get_secret_value(),
            settings.gemini_model,
            timeout_seconds=settings.assistant_timeout_seconds,
        )
    return None


def configured(settings: Settings) -> Providers:
    """Providers from settings: Gemini for evaluation and transcription when a key is set.
    No pronunciation assessor is configured, so Pronunciation is reported as not assessed."""
    assistant = _assistant(settings)
    if settings.gemini_api_key is None:
        return Providers(assistant=assistant)
    key = settings.gemini_api_key.get_secret_value()
    return Providers(
        llm=GeminiLLM(key, settings.gemini_model),
        llm_model=settings.gemini_model,
        stt=GeminiSTT(key, settings.gemini_model),
        assistant=assistant,
    )


def providers(settings: Settings) -> Providers:
    return _factory(settings) if _factory is not None else configured(settings)
