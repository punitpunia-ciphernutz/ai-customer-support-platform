"""Day 6 automation REST API tests."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.infrastructure.database.models import Organization, User
from app.infrastructure.database.session import AsyncSessionLocal
from app.main import app
from app.modules.auth.security import create_access_token


@pytest.fixture
async def api_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def auth_headers() -> dict[str, str]:
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).limit(1))).scalar_one()
        token = create_access_token(user.id, {"organization_id": user.organization_id})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_automations(api_client: AsyncClient, auth_headers: dict[str, str]) -> None:
    r = await api_client.get("/api/v1/automations", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_create_automation(api_client: AsyncClient, auth_headers: dict[str, str]) -> None:
    body = {
        "name": "API Test Automation",
        "enabled": True,
        "trigger": {"type": "CONVERSATION_CREATED"},
        "conditions": None,
        "actions": [{"type": "SET_PRIORITY", "value": "HIGH"}],
        "priority": 5,
    }
    r = await api_client.post("/api/v1/automations", headers=auth_headers, json=body)
    assert r.status_code == 201
    assert r.json()["name"] == "API Test Automation"
