import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Environment, Settings
from app.main import create_app

UNREACHABLE_DB = "postgresql://test:test@127.0.0.1:9/test"
UNREACHABLE_REDIS = "redis://127.0.0.1:9/0"
TEST_SECRET = "test-only-secret-key-0123456789abcdef"


def test_required_settings_missing_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    missing = {err["loc"][0] for err in excinfo.value.errors()}
    assert missing == {"database_url", "redis_url"}


def test_invalid_database_url_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="mysql://x@y/z", redis_url=UNREACHABLE_REDIS)


def test_settings_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_DB)
    monkeypatch.setenv("REDIS_URL", UNREACHABLE_REDIS)
    monkeypatch.setenv("AUTH_SECRET_KEY", TEST_SECRET)
    settings = Settings()
    assert settings.app_env is Environment.STAGING


def test_debug_logging_forbidden_in_production() -> None:
    with pytest.raises(ValidationError, match="DEBUG"):
        Settings(
            app_env="production",
            log_level="DEBUG",
            database_url=UNREACHABLE_DB,
            redis_url=UNREACHABLE_REDIS,
        )


async def test_openapi_docs_disabled_in_production() -> None:
    settings = Settings(
        app_env="production",
        database_url=UNREACHABLE_DB,
        redis_url=UNREACHABLE_REDIS,
        auth_secret_key=TEST_SECRET,
        public_app_url="https://app.example.test",
    )
    transport = httpx.ASGITransport(app=create_app(settings))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        assert (await client.get("/api/v1/openapi.json")).status_code == 404
        assert (await client.get("/api/v1/docs")).status_code == 404


async def test_openapi_available_outside_production(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/openapi.json")).status_code == 200


async def test_request_id_generated_when_absent(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    assert len(response.headers["x-request-id"]) == 36  # uuid4


async def test_safe_request_id_is_propagated(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz", headers={"X-Request-ID": "trace-abc-12345"})
    assert response.headers["x-request-id"] == "trace-abc-12345"


async def test_unsafe_request_id_is_replaced(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz", headers={"X-Request-ID": "bad id\r\ninjected"})
    assert response.headers["x-request-id"] != "bad id\r\ninjected"
    assert len(response.headers["x-request-id"]) == 36
