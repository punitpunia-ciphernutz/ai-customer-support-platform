"""Teams membership and CRUD API tests."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.infrastructure.database.models import (
    ChannelType,
    Conversation,
    Customer,
    Role,
    RoleName,
    User,
)
from app.infrastructure.database.session import AsyncSessionLocal
from app.main import app
from app.modules.auth.security import create_access_token


@pytest.fixture
async def api_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _token_for_role(role_name: RoleName) -> tuple[dict[str, str], str, str]:
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(
                select(User)
                .join(Role, Role.id == User.role_id)
                .where(Role.name == role_name)
                .limit(1)
            )
        ).scalar_one()
        token = create_access_token(user.id, {"organization_id": user.organization_id})
        return {"Authorization": f"Bearer {token}"}, user.id, user.organization_id


@pytest.fixture
async def manager_auth() -> tuple[dict[str, str], str, str]:
    return await _token_for_role(RoleName.MANAGER)


@pytest.fixture
async def agent_auth() -> tuple[dict[str, str], str, str]:
    return await _token_for_role(RoleName.AGENT)


@pytest.mark.asyncio
async def test_list_teams_includes_member_count(
    api_client: AsyncClient, manager_auth: tuple[dict[str, str], str, str]
) -> None:
    headers, _, _ = manager_auth
    r = await api_client.get("/api/v1/teams", headers=headers)
    assert r.status_code == 200
    teams = r.json()
    assert isinstance(teams, list)
    assert len(teams) >= 1
    assert "member_count" in teams[0]
    assert isinstance(teams[0]["member_count"], int)


@pytest.mark.asyncio
async def test_list_users_includes_teams(
    api_client: AsyncClient, manager_auth: tuple[dict[str, str], str, str]
) -> None:
    headers, _, _ = manager_auth
    r = await api_client.get("/api/v1/users", headers=headers)
    assert r.status_code == 200
    users = r.json()
    assert isinstance(users, list)
    assert len(users) >= 1
    assert "teams" in users[0]
    agent = next((u for u in users if u["email"] == "agent@example.com"), None)
    assert agent is not None
    team_names = {t["name"] for t in agent["teams"]}
    assert "Support" in team_names or "Billing" in team_names


@pytest.mark.asyncio
async def test_membership_add_duplicate_and_remove(
    api_client: AsyncClient, manager_auth: tuple[dict[str, str], str, str]
) -> None:
    headers, _, org_id = manager_auth
    suffix = uuid.uuid4().hex[:8]

    create = await api_client.post(
        "/api/v1/teams",
        headers=headers,
        json={"name": f"QA Team {suffix}", "description": "temp"},
    )
    assert create.status_code == 201
    team_id = create.json()["id"]

    async with AsyncSessionLocal() as session:
        manager = (
            await session.execute(
                select(User)
                .join(Role, Role.id == User.role_id)
                .where(Role.name == RoleName.MANAGER, User.organization_id == org_id)
                .limit(1)
            )
        ).scalar_one()
        member_user_id = manager.id

    add = await api_client.post(
        f"/api/v1/teams/{team_id}/members",
        headers=headers,
        json={"user_id": member_user_id},
    )
    assert add.status_code == 201
    assert add.json()["user_id"] == member_user_id

    dup = await api_client.post(
        f"/api/v1/teams/{team_id}/members",
        headers=headers,
        json={"user_id": member_user_id},
    )
    assert dup.status_code == 409

    members = await api_client.get(f"/api/v1/teams/{team_id}/members", headers=headers)
    assert members.status_code == 200
    assert any(m["user_id"] == member_user_id for m in members.json())

    detail = await api_client.get(f"/api/v1/teams/{team_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["member_count"] == 1

    remove = await api_client.delete(
        f"/api/v1/teams/{team_id}/members/{member_user_id}",
        headers=headers,
    )
    assert remove.status_code == 204

    members_after = await api_client.get(f"/api/v1/teams/{team_id}/members", headers=headers)
    assert members_after.status_code == 200
    assert members_after.json() == []

    delete = await api_client.delete(f"/api/v1/teams/{team_id}", headers=headers)
    assert delete.status_code == 204


@pytest.mark.asyncio
async def test_delete_team_blocked_when_conversation_assigned(
    api_client: AsyncClient, manager_auth: tuple[dict[str, str], str, str]
) -> None:
    headers, _, org_id = manager_auth
    suffix = uuid.uuid4().hex[:8]

    create = await api_client.post(
        "/api/v1/teams",
        headers=headers,
        json={"name": f"Assigned Team {suffix}", "description": None},
    )
    assert create.status_code == 201
    team_id = create.json()["id"]

    async with AsyncSessionLocal() as session:
        customer = Customer(organization_id=org_id, name=f"Teams Test {suffix}")
        session.add(customer)
        await session.flush()
        session.add(
            Conversation(
                organization_id=org_id,
                customer_id=customer.id,
                channel=ChannelType.WEB_CHAT,
                assigned_team_id=team_id,
            )
        )
        await session.commit()

    blocked = await api_client.delete(f"/api/v1/teams/{team_id}", headers=headers)
    assert blocked.status_code == 409
    assert "assigned" in blocked.json()["detail"].lower()

    async with AsyncSessionLocal() as session:
        conv = await session.scalar(
            select(Conversation).where(Conversation.assigned_team_id == team_id)
        )
        assert conv is not None
        conv.assigned_team_id = None
        await session.commit()

    allowed = await api_client.delete(f"/api/v1/teams/{team_id}", headers=headers)
    assert allowed.status_code == 204


@pytest.mark.asyncio
async def test_update_team_and_duplicate_name(
    api_client: AsyncClient, manager_auth: tuple[dict[str, str], str, str]
) -> None:
    headers, _, _ = manager_auth
    suffix = uuid.uuid4().hex[:8]

    a = await api_client.post(
        "/api/v1/teams",
        headers=headers,
        json={"name": f"Alpha {suffix}", "description": "a"},
    )
    b = await api_client.post(
        "/api/v1/teams",
        headers=headers,
        json={"name": f"Beta {suffix}", "description": "b"},
    )
    assert a.status_code == 201 and b.status_code == 201
    team_a = a.json()["id"]
    team_b = b.json()["id"]

    patched = await api_client.patch(
        f"/api/v1/teams/{team_a}",
        headers=headers,
        json={"description": "updated"},
    )
    assert patched.status_code == 200
    assert patched.json()["description"] == "updated"

    conflict = await api_client.patch(
        f"/api/v1/teams/{team_b}",
        headers=headers,
        json={"name": f"Alpha {suffix}"},
    )
    assert conflict.status_code == 409

    await api_client.delete(f"/api/v1/teams/{team_a}", headers=headers)
    await api_client.delete(f"/api/v1/teams/{team_b}", headers=headers)


@pytest.mark.asyncio
async def test_agent_cannot_write_teams(
    api_client: AsyncClient, agent_auth: tuple[dict[str, str], str, str]
) -> None:
    headers, _, _ = agent_auth
    r = await api_client.post(
        "/api/v1/teams",
        headers=headers,
        json={"name": f"Forbidden {uuid.uuid4().hex[:6]}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_unknown_team_returns_404(
    api_client: AsyncClient, manager_auth: tuple[dict[str, str], str, str]
) -> None:
    headers, _, _ = manager_auth
    fake_id = str(uuid.uuid4())
    r = await api_client.get(f"/api/v1/teams/{fake_id}", headers=headers)
    assert r.status_code == 404
