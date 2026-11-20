"""Public interface of the assistant module: mounting its API."""

from fastapi import FastAPI

from app.modules.assistant.router import router

__all__ = ["install"]


def install(app: FastAPI) -> None:
    app.include_router(router)
