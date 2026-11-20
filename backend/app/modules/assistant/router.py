"""Site assistant API under /api/v1/assistant. Open to guests and signed-in users.

POST is CSRF-protected by the identity middleware (guests use the anonymous token). Answers are
never cached. A signed-in user's quota is keyed by user id; a guest's by client IP.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from app.core.config import Settings
from app.core.errors import PROBLEM_MEDIA_TYPE
from app.modules.assistant import service
from app.modules.assistant.schemas import ChatIn, ChatOut, StatusOut
from app.modules.identity import api as identity

MaybeUser = Annotated[identity.CurrentUser | None, Depends(identity.optional_current_user)]
Limiter = Annotated[identity.RateLimiter, Depends(identity.rate_limiter)]


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


AppSettings = Annotated[Settings, Depends(_settings)]


def _problems(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {c: {"description": "Problem", "content": {PROBLEM_MEDIA_TYPE: {}}} for c in codes}


router = APIRouter(
    prefix="/api/v1/assistant",
    tags=["assistant"],
    dependencies=[Depends(_no_store)],
)


@router.get("/status", response_model=StatusOut)
async def status(settings: AppSettings) -> StatusOut:
    return StatusOut(available=service.is_available(settings))


@router.post("/chat", response_model=ChatOut, responses=_problems(422, 429, 503))
async def chat(
    data: ChatIn, request: Request, user: MaybeUser, limiter: Limiter, settings: AppSettings
) -> ChatOut:
    if user is not None:
        subject = f"user:{user.id}"
    else:
        subject = f"ip:{request.client.host if request.client else 'unknown'}"
    await service.enforce_quota(limiter, settings, subject=subject, signed_in=user is not None)
    text = await service.chat(
        settings,
        data,
        user=user,
        correlation_id=str(getattr(request.state, "request_id", "") or "assistant"),
    )
    return ChatOut(content=text)
