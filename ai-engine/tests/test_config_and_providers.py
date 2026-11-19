import pytest
from pydantic import ValidationError

from ielts_ai.config import AIEngineConfig, ProviderRoute
from ielts_ai.providers import LLMCapabilities, Operation, UsageEvent


def test_routes_are_returned_in_priority_order() -> None:
    config = AIEngineConfig(
        routes={
            "writing.criterion": (
                ProviderRoute(provider="primary", model="m1"),
                ProviderRoute(provider="fallback", model="m2"),
            )
        }
    )
    assert [r.provider for r in config.routes_for("writing.criterion")] == ["primary", "fallback"]


def test_unknown_feature_has_no_silent_default() -> None:
    with pytest.raises(KeyError, match="No provider routes"):
        AIEngineConfig().routes_for("coach.chat")


def test_route_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ProviderRoute(provider="p", model="m", api_key="should-not-live-here")  # type: ignore[call-arg]


def test_usage_event_rejects_negative_counts() -> None:
    with pytest.raises(ValidationError):
        UsageEvent(
            feature="writing.criterion",
            provider="p",
            model="m",
            operation=Operation.LLM,
            correlation_id="c",
            succeeded=True,
            latency_ms=10,
            input_tokens=-1,
        )


def test_capabilities_default_to_unsupported() -> None:
    caps = LLMCapabilities(max_context_tokens=8000)
    assert not caps.structured_output
    assert not caps.tool_calling
    assert not caps.streaming
