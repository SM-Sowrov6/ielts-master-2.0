"""Public interface of the admin module: the application factory mounts its router."""

from fastapi import FastAPI

from app.modules.admin.content_router import router as content_router
from app.modules.admin.router import router
from app.modules.admin.speaking_router import router as speaking_router

__all__ = ["install"]


def install(app: FastAPI) -> None:
    app.include_router(router)
    app.include_router(content_router)
    app.include_router(speaking_router)
