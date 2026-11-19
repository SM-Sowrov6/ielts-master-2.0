"""Public interface of the writing module: mounting the candidate API and the evaluation job."""

from fastapi import FastAPI

from app.core.outbox import OutboxHandler
from app.modules.writing.router import router
from app.modules.writing.service import TOPIC, handle_evaluate

OUTBOX_HANDLERS: dict[str, OutboxHandler] = {TOPIC: handle_evaluate}

__all__ = ["OUTBOX_HANDLERS", "install"]


def install(app: FastAPI) -> None:
    app.include_router(router)
