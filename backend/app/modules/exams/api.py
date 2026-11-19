"""Public interface of the exams module: mounting the candidate API and the expiry sweep."""

from fastapi import FastAPI

from app.modules.exams.router import router
from app.modules.exams.service import sweep_expired

__all__ = ["install", "sweep_expired"]


def install(app: FastAPI) -> None:
    app.include_router(router)
