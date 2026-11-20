"""Assistant chat: quota checks, context assembly and the provider call (via the AI gateway).

Privacy: the only user detail sent to the model is the first name of a signed-in user. No
account data, progress or page contents are sent. Nothing is stored; logs carry only metadata
(model, latency, token counts), never message text.
"""

import asyncio
import time

import structlog

from app.core import ai
from app.core.config import Settings
from app.modules.assistant import knowledge
from app.modules.assistant.errors import (
    AssistantBusyError,
    AssistantRateLimitedError,
    AssistantUnavailableError,
)
from app.modules.assistant.schemas import ChatIn
from app.modules.identity import api as identity
from ielts_ai.graphs import assistant as workflow

log = structlog.get_logger("app.assistant")


def is_available(settings: Settings) -> bool:
    return ai.providers(settings).assistant is not None


def _rules(settings: Settings, signed_in: bool) -> tuple[identity.Rule, identity.Rule]:
    if signed_in:
        return (
            identity.Rule("assistant:user:min", settings.assistant_user_per_minute, 60),
            identity.Rule("assistant:user:day", settings.assistant_user_per_day, 86400),
        )
    return (
        identity.Rule("assistant:guest:min", settings.assistant_guest_per_minute, 60),
        identity.Rule("assistant:guest:day", settings.assistant_guest_per_day, 86400),
    )


async def enforce_quota(
    limiter: identity.RateLimiter, settings: Settings, *, subject: str, signed_in: bool
) -> None:
    """Fixed-window quotas per user (signed in) or per client IP (guest). Fails closed (503)
    when Redis is unreachable, like the other rate-limited endpoints."""
    for rule in _rules(settings, signed_in):
        count, retry_after = await limiter.hit(rule, subject)
        if count > rule.limit:
            raise AssistantRateLimitedError(headers={"Retry-After": str(retry_after)})


def first_name(user: identity.CurrentUser | None) -> str | None:
    if user is None:
        return None
    parts = user.full_name.split()
    return parts[0][:40] if parts else None


async def chat(
    settings: Settings,
    data: ChatIn,
    *,
    user: identity.CurrentUser | None,
    correlation_id: str,
) -> str:
    llm = ai.providers(settings).assistant
    if llm is None:
        raise AssistantUnavailableError
    history = [workflow.ChatTurn(role=m.role, content=m.content) for m in data.messages]
    context = workflow.AssistantContext(
        site_pages=knowledge.site_pages(),
        page=knowledge.page_context(data.page.path if data.page else None),
        first_name=first_name(user),
        signed_in=user is not None,
    )
    started = time.monotonic()
    try:
        # Small grace over the provider deadline; stays under common 30 s proxy timeouts.
        async with asyncio.timeout(settings.assistant_timeout_seconds + 2):
            result = await workflow.reply(
                llm,
                history,
                context,
                correlation_id=correlation_id,
                max_output_tokens=settings.assistant_max_output_tokens,
            )
    except TimeoutError:
        log.warning("assistant.timeout", provider=llm.name)
        raise AssistantBusyError(headers={"Retry-After": "10"}) from None
    except Exception as exc:  # provider failures of any kind: never leak details
        if getattr(exc, "rate_limited", False):
            log.warning("assistant.provider_rate_limited", provider=llm.name)
            raise AssistantBusyError(headers={"Retry-After": "30"}) from None
        log.error("assistant.provider_failed", provider=llm.name, error=type(exc).__name__)
        raise AssistantUnavailableError from None
    log.info(
        "assistant.reply",
        provider=llm.name,
        model=result.model,
        prompt_version=result.prompt_version,
        latency_ms=int((time.monotonic() - started) * 1000),
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        signed_in=user is not None,
    )
    return result.text
