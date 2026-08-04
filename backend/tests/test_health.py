from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.main import _validate_settings_on_startup, app, get_readiness_probes


@pytest.mark.parametrize(
    "jwt_secret",
    [
        "change-me-in-production",
        "replace-with-at-least-32-random-characters",
        "too-short",
    ],
)
def test_startup_rejects_insecure_jwt_secrets(monkeypatch, jwt_secret):
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(settings, "jwt_secret", jwt_secret)

    with pytest.raises(SystemExit, match="JWT_SECRET"):
        _validate_settings_on_startup()


def test_startup_accepts_non_placeholder_jwt_secret(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(settings, "jwt_secret", "a-valid-test-secret-with-32-characters")

    _validate_settings_on_startup()


@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"


@pytest.mark.asyncio
async def test_liveness_does_not_run_dependency_probes(client):
    probe = AsyncMock()
    app.dependency_overrides[get_readiness_probes] = lambda: [probe]
    try:
        response = await client.get("/health/live")
    finally:
        app.dependency_overrides.pop(get_readiness_probes, None)

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "alive"
    probe.check.assert_not_awaited()


@pytest.mark.asyncio
async def test_readiness_reports_all_healthy_dependencies(client):
    database = AsyncMock(name="database")
    database.name = "database"
    database.check = AsyncMock(return_value=None)
    redis = AsyncMock(name="redis")
    redis.name = "redis"
    redis.check = AsyncMock(return_value=None)
    app.dependency_overrides[get_readiness_probes] = lambda: [database, redis]
    try:
        response = await client.get("/health/ready")
    finally:
        app.dependency_overrides.pop(get_readiness_probes, None)

    assert response.status_code == 200
    assert response.json()["data"] == {
        "status": "ready",
        "checks": {"database": "ok", "redis": "ok"},
    }


@pytest.mark.asyncio
async def test_readiness_returns_503_when_a_dependency_is_unavailable(client):
    database = AsyncMock(name="database")
    database.name = "database"
    database.check = AsyncMock(side_effect=RuntimeError("connection refused"))
    app.dependency_overrides[get_readiness_probes] = lambda: [database]
    try:
        response = await client.get("/health/ready")
    finally:
        app.dependency_overrides.pop(get_readiness_probes, None)

    assert response.status_code == 503
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert body["data"] == {
        "status": "not_ready",
        "checks": {"database": "unavailable"},
    }
