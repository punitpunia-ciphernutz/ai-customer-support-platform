from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.infrastructure.health import collect_health
from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_endpoints_return_simple_status_map(client: AsyncClient):
    fake = {
        "status": "healthy",
        "api": "healthy",
        "db": "healthy",
        "redis": "healthy",
        "celery": "healthy",
        "worker": "healthy",
        "llm": "healthy",
        "storage": "healthy",
    }
    with patch("app.main.collect_health", new=AsyncMock(return_value=fake)):
        with patch("app.api.router.collect_health", new=AsyncMock(return_value=fake)):
            r = await client.get("/health")
            assert r.status_code == 200
            assert r.json() == fake
            r2 = await client.get("/api/v1/health")
            assert r2.status_code == 200
            assert r2.json() == fake


@pytest.mark.asyncio
async def test_collect_health_marks_unhealthy_when_llm_fails(monkeypatch: pytest.MonkeyPatch):
    async def ok() -> str:
        return "healthy"

    async def llm_down() -> str:
        return "unhealthy"

    monkeypatch.setattr("app.infrastructure.health._check_api", ok)
    monkeypatch.setattr("app.infrastructure.health._check_database", ok)
    monkeypatch.setattr("app.infrastructure.health._check_redis", ok)
    monkeypatch.setattr("app.infrastructure.health._check_celery", ok)
    monkeypatch.setattr("app.infrastructure.health._check_worker", ok)
    monkeypatch.setattr("app.infrastructure.health._check_llm", llm_down)
    monkeypatch.setattr("app.infrastructure.health._check_storage", ok)

    payload = await collect_health()
    assert payload == {
        "status": "unhealthy",
        "api": "healthy",
        "db": "healthy",
        "redis": "healthy",
        "celery": "healthy",
        "worker": "healthy",
        "llm": "unhealthy",
        "storage": "healthy",
    }
    assert set(payload) == {"status", "api", "db", "redis", "celery", "worker", "llm", "storage"}
    assert all(isinstance(v, str) and v in {"healthy", "unhealthy"} for v in payload.values())


@pytest.mark.asyncio
async def test_collect_health_marks_unhealthy_when_database_fails(monkeypatch: pytest.MonkeyPatch):
    async def ok() -> str:
        return "healthy"

    async def db_down() -> str:
        return "unhealthy"

    monkeypatch.setattr("app.infrastructure.health._check_api", ok)
    monkeypatch.setattr("app.infrastructure.health._check_database", db_down)
    monkeypatch.setattr("app.infrastructure.health._check_redis", ok)
    monkeypatch.setattr("app.infrastructure.health._check_celery", ok)
    monkeypatch.setattr("app.infrastructure.health._check_worker", ok)
    monkeypatch.setattr("app.infrastructure.health._check_llm", ok)
    monkeypatch.setattr("app.infrastructure.health._check_storage", ok)

    payload = await collect_health()
    assert payload["status"] == "unhealthy"
    assert payload["db"] == "unhealthy"
    assert payload["api"] == "healthy"
    assert "email" not in payload
    assert "checks" not in payload
    assert "error" not in str(payload)
