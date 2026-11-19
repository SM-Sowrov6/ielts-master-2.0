from collections.abc import Sequence

import httpx
from fastapi import FastAPI

from app.core.health import ReadinessCheck, get_readiness_checks


class _StaticCheck:
    def __init__(self, name: str, *, healthy: bool) -> None:
        self.name = name
        self._healthy = healthy

    async def check(self) -> None:
        if not self._healthy:
            raise ConnectionError("dependency down")


def _override(app: FastAPI, checks: Sequence[ReadinessCheck]) -> None:
    app.dependency_overrides[get_readiness_checks] = lambda: checks


async def test_healthz_is_ok_without_dependencies(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_ok_when_all_checks_pass(app: FastAPI, client: httpx.AsyncClient) -> None:
    _override(app, [_StaticCheck("postgres", healthy=True), _StaticCheck("redis", healthy=True)])
    response = await client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"postgres": "ok", "redis": "ok"}}


async def test_readyz_503_when_a_check_fails(app: FastAPI, client: httpx.AsyncClient) -> None:
    _override(app, [_StaticCheck("postgres", healthy=True), _StaticCheck("redis", healthy=False)])
    response = await client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body == {"status": "unavailable", "checks": {"postgres": "ok", "redis": "unavailable"}}
    assert "dependency down" not in response.text  # error details are never exposed


async def test_readyz_real_checks_report_unreachable_dependencies(
    client: httpx.AsyncClient,
) -> None:
    # Uses the real PostgresCheck/RedisCheck against closed loopback ports.
    response = await client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"] == {"postgres": "unavailable", "redis": "unavailable"}
