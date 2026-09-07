"""Day 6 automation REST API tests."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.infrastructure.database.models import Role, RoleName, User
from app.infrastructure.database.session import AsyncSessionLocal
from app.main import app
from app.modules.auth.security import create_access_token


@pytest.fixture
async def api_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _auth_for(role_name: RoleName) -> dict[str, str]:
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(
                select(User)
                .join(Role, Role.id == User.role_id)
                .where(Role.name == role_name, User.is_active.is_(True))
                .options(selectinload(User.role))
                .limit(1)
            )
        ).scalar_one()
        token = create_access_token(user.id, {"organization_id": user.organization_id})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def auth_headers() -> dict[str, str]:
    """Admin has ai.write required for create/enable/disable."""
    return await _auth_for(RoleName.ADMIN)


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


@pytest.mark.asyncio
async def test_enable_disable_automation(api_client: AsyncClient, auth_headers: dict[str, str]) -> None:
    create = await api_client.post(
        "/api/v1/automations",
        headers=auth_headers,
        json={
            "name": "Toggle Test Automation",
            "enabled": True,
            "trigger": {"type": "MESSAGE_RECEIVED"},
            "conditions": None,
            "actions": [{"type": "SET_PRIORITY", "value": "LOW"}],
            "priority": 1,
        },
    )
    assert create.status_code == 201
    automation_id = create.json()["id"]

    disabled = await api_client.post(f"/api/v1/automations/{automation_id}/disable", headers=auth_headers)
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert disabled.json()["updated_at"]

    enabled = await api_client.post(f"/api/v1/automations/{automation_id}/enable", headers=auth_headers)
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True
    assert enabled.json()["updated_at"]


@pytest.mark.asyncio
async def test_delete_automation(api_client: AsyncClient, auth_headers: dict[str, str]) -> None:
    create = await api_client.post(
        "/api/v1/automations",
        headers=auth_headers,
        json={
            "name": "Delete Test Automation",
            "enabled": True,
            "trigger": {"type": "MISSED_CHAT"},
            "conditions": None,
            "actions": [{"type": "SET_PRIORITY", "value": "HIGH"}],
            "priority": 2,
        },
    )
    assert create.status_code == 201
    automation_id = create.json()["id"]

    deleted = await api_client.delete(f"/api/v1/automations/{automation_id}", headers=auth_headers)
    assert deleted.status_code == 204

    missing = await api_client.get(f"/api/v1/automations/{automation_id}", headers=auth_headers)
    assert missing.status_code == 404
