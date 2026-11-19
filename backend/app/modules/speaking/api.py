"""Public interface of the speaking module: mounting the candidate API and the evaluation job."""

from fastapi import FastAPI

from app.core.outbox import OutboxHandler
from app.modules.speaking import rooms, voice
from app.modules.speaking.room_router import examiner_out, internal
from app.modules.speaking.room_router import router as room_router
from app.modules.speaking.router import router
from app.modules.speaking.service import TOPIC, handle_evaluate

OUTBOX_HANDLERS: dict[str, OutboxHandler] = {TOPIC: handle_evaluate}

__all__ = ["OUTBOX_HANDLERS", "examiner_out", "install", "rooms", "voice"]


def install(app: FastAPI) -> None:
    from app.modules.speaking.livekit_voice import LiveKitVoice, configured

    settings = getattr(app.state, "settings", None)
    if settings is not None and configured(settings):
        voice.register(LiveKitVoice(settings))
    app.include_router(room_router)
    app.include_router(router)
    app.include_router(internal)
