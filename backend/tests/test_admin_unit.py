"""Admin console: structural authorization checks (no database needed)."""

import importlib.util
from pathlib import Path
from types import ModuleType

import httpx
import pytest
from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.modules.admin.content_router import router as content_router
from app.modules.admin.router import router as admin_router
from app.modules.admin.speaking_router import router as speaking_router
from app.modules.identity.deps import require_staff, require_staff_permission
from app.modules.identity.provisioning import ProvisioningError
from app.modules.identity.router import router as identity_router

ADMIN_CLI = Path(__file__).resolve().parents[2] / "scripts" / "admin_cli.py"


def _admin_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location("admin_cli_unit", ADMIN_CLI)
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _calls(dependant: Dependant) -> set[object]:
    found: set[object] = {dependant.call}
    for sub in dependant.dependencies:
        found |= _calls(sub)
    return found


def _admin_routes() -> list[APIRoute]:
    return [
        r
        for router in (admin_router, content_router, speaking_router, identity_router)
        for r in router.routes
        if isinstance(r, APIRoute) and r.path.startswith("/api/v1/admin")
    ]


def test_every_admin_route_passes_the_staff_gate(app: FastAPI) -> None:
    routes = _admin_routes()
    published = {p for p in app.openapi()["paths"] if p.startswith("/api/v1/admin")}
    assert published == {r.path for r in routes}  # no admin route lives anywhere else
    assert {r.path for r in routes} >= {
        "/api/v1/admin/session",
        "/api/v1/admin/overview/users",
        "/api/v1/admin/overview/content",
        "/api/v1/admin/audit-logs",
    }
    for route in routes:
        assert require_staff in _calls(route.dependant), route.path


async def test_admin_routes_refuse_requests_without_a_session(client: httpx.AsyncClient) -> None:
    for path in (
        "/api/v1/admin/session",
        "/api/v1/admin/overview/users",
        "/api/v1/admin/overview/content",
        "/api/v1/admin/audit-logs",
    ):
        response = await client.get(path)
        assert response.status_code == 401, path
        assert response.json()["code"] == "not_authenticated"


async def test_admin_mutations_without_csrf_are_blocked(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/admin/overview/users")
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


def test_permission_gate_needs_at_least_one_permission() -> None:
    with pytest.raises(ValueError, match="at least one"):
        require_staff_permission()


def test_cli_never_takes_a_password_argument() -> None:
    cli = _admin_cli()
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["create-staff", "a@example.test", "--full-name", "A", "--password", "x"])


def test_cli_password_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = _admin_cli()
    monkeypatch.setenv("UNIT_ADMIN_PASSWORD", "from the secret store 123")
    assert cli.read_password("UNIT_ADMIN_PASSWORD") == "from the secret store 123"
    monkeypatch.delenv("UNIT_ADMIN_PASSWORD")
    with pytest.raises(ProvisioningError, match="is empty"):
        cli.read_password("UNIT_ADMIN_PASSWORD")
    with pytest.raises(ProvisioningError, match="No terminal"):
        cli.read_password(None, interactive=False)
    answers = iter(["typed passphrase 1", "typed passphrase 2"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: next(answers))
    with pytest.raises(ProvisioningError, match="do not match"):
        cli.read_password(None, interactive=True)
