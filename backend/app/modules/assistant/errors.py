"""Assistant errors with stable problem codes (no provider details are ever returned)."""

from typing import ClassVar

from app.core.errors import DomainError


class AssistantUnavailableError(DomainError):
    status_code: ClassVar[int] = 503
    code: ClassVar[str] = "assistant_unavailable"
    title: ClassVar[str] = "The assistant is not available right now. Please try again later."


class AssistantBusyError(DomainError):
    """Every configured (free) model is rate limited upstream."""

    status_code: ClassVar[int] = 503
    code: ClassVar[str] = "assistant_busy"
    title: ClassVar[str] = "The assistant is busy right now. Please try again in a moment."


class AssistantRateLimitedError(DomainError):
    status_code: ClassVar[int] = 429
    code: ClassVar[str] = "assistant_rate_limited"
    title: ClassVar[str] = "You have sent a lot of messages. Please wait a little and try again."
