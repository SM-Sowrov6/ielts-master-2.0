"""Injected AI-engine configuration. Loaded by the backend / voice engine and passed in."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProviderRoute(BaseModel):
    """One candidate provider/model for a feature; routes are tried in priority order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    weight: int = Field(default=1, ge=1)
    timeout_seconds: float = Field(default=30.0, gt=0, le=600)


class AIEngineConfig(BaseModel):
    """Feature-key → ordered provider routes (e.g. "writing.criterion" → [primary, fallback])."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    routes: dict[str, tuple[ProviderRoute, ...]] = Field(default_factory=dict)

    def routes_for(self, feature: str) -> tuple[ProviderRoute, ...]:
        try:
            return self.routes[feature]
        except KeyError:
            raise KeyError(f"No provider routes configured for feature {feature!r}") from None
