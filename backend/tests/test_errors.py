from typing import ClassVar

import httpx
import pytest
from fastapi import FastAPI

from app.core.errors import PROBLEM_MEDIA_TYPE, DomainError


class _ExampleConflictError(DomainError):
    status_code: ClassVar[int] = 409
    code: ClassVar[str] = "example_conflict"
    title: ClassVar[str] = "Example conflict"


@pytest.fixture
def app_with_routes(app: FastAPI) -> FastAPI:
    @app.get("/_test/domain-error")
    async def domain_error() -> None:
        raise _ExampleConflictError("conflicting state")

    @app.get("/_test/crash")
    async def crash() -> None:
        raise RuntimeError("secret internal detail")

    @app.get("/_test/items/{item_id}")
    async def item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    return app


@pytest.mark.usefixtures("app_with_routes")
async def test_domain_error_maps_to_problem_json(client: httpx.AsyncClient) -> None:
    response = await client.get("/_test/domain-error")
    assert response.status_code == 409
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    body = response.json()
    assert body["code"] == "example_conflict"
    assert body["type"] == "urn:ielts-master:problem:example_conflict"
    assert body["detail"] == "conflicting state"
    assert body["instance"] == "/_test/domain-error"
    assert body["request_id"] == response.headers["x-request-id"]


@pytest.mark.usefixtures("app_with_routes")
async def test_unhandled_error_is_generic_500(client: httpx.AsyncClient) -> None:
    response = await client.get("/_test/crash")
    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "secret internal detail" not in response.text


@pytest.mark.usefixtures("app_with_routes")
async def test_validation_error_lists_fields(client: httpx.AsyncClient) -> None:
    response = await client.get("/_test/items/not-a-number")
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["errors"][0]["loc"] == ["path", "item_id"]


async def test_unknown_route_is_problem_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["code"] == "not_found"
