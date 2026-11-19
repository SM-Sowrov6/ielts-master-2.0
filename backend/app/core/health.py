"""Liveness (`/healthz`) and readiness (`/readyz`) endpoints (docs/API_SPECIFICATION.md §11).

Liveness never touches dependencies. Readiness checks PostgreSQL and Redis with a timeout and
returns 503 if any dependency is unavailable. Error details are logged, never returned.
"""

import asyncio
from collections.abc import Sequence
from typing import Annotated, Literal, Protocol

import structlog
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings

log = structlog.get_logger("app.health")

CheckStatus = Literal["ok", "unavailable"]


class ReadinessCheck(Protocol):
    name: str

    async def check(self) -> None:
        """Return normally if healthy; raise any exception if not."""
        ...


class PostgresCheck:
    """Runs `SELECT 1` through the application's pooled engine (the real connection path)."""

    name = "postgres"

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def check(self) -> None:
        async with self._engine.connect() as conn:
            await conn.execute(text("SELECT 1"))


class RedisCheck:
    name = "redis"

    def __init__(self, url: str, timeout: float) -> None:
        self._url = url
        self._timeout = timeout

    async def check(self) -> None:
        client = Redis.from_url(
            self._url, socket_timeout=self._timeout, socket_connect_timeout=self._timeout
        )
        try:
            await client.ping()
        finally:
            await client.aclose()


class LivenessResponse(BaseModel):
    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    status: CheckStatus
    checks: dict[str, CheckStatus]


def get_readiness_checks(request: Request) -> Sequence[ReadinessCheck]:
    settings: Settings = request.app.state.settings
    timeout = settings.readiness_timeout_seconds
    return (
        PostgresCheck(request.app.state.db_engine),
        RedisCheck(str(settings.redis_url), timeout),
    )


async def _run_check(check: ReadinessCheck, limit_seconds: float) -> CheckStatus:
    try:
        async with asyncio.timeout(limit_seconds):
            await check.check()
    except Exception as exc:  # any failure means "not ready"; details only go to logs
        log.warning("readiness.check_failed", check=check.name, error_type=type(exc).__name__)
        return "unavailable"
    return "ok"


router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=LivenessResponse)
async def healthz() -> LivenessResponse:
    return LivenessResponse(status="ok")


@router.get(
    "/readyz",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def readyz(
    request: Request,
    response: Response,
    checks: Annotated[Sequence[ReadinessCheck], Depends(get_readiness_checks)],
) -> ReadinessResponse:
    settings: Settings = request.app.state.settings
    # Allow a little slack over the per-check timeout for connection teardown.
    timeout = settings.readiness_timeout_seconds + 0.5
    results = await asyncio.gather(*(_run_check(c, timeout) for c in checks))
    statuses = {c.name: r for c, r in zip(checks, results, strict=True)}
    ready = all(s == "ok" for s in statuses.values())
    if not ready:
        response.status_code = 503
    return ReadinessResponse(status="ok" if ready else "unavailable", checks=statuses)
