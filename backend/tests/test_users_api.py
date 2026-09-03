"""User admin RBAC API tests."""

import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.infrastructure.database.models import AuditLog, Role, RoleName, User
from app.infrastructure.database.session import AsyncSessionLocal
from app.main import app
from app.modules.auth.security import create_access_token


@pytest.fixture
async def api_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _auth_for(role_name: RoleName) -> tuple[dict[str, str], SimpleNamespace]:
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
        actor = SimpleNamespace(id=user.id, organization_id=user.organization_id, email=user.email)
        token = create_access_token(user.id, {"organization_id": user.organization_id})
    return {"Authorization": f"Bearer {token}"}, actor


@pytest.fixture
async def manager_auth() -> tuple[dict[str, str], SimpleNamespace]:
    return await _auth_for(RoleName.MANAGER)


@pytest.fixture
async def admin_auth() -> tuple[dict[str, str], SimpleNamespace]:
    return await _auth_for(RoleName.ADMIN)


@pytest.fixture
async def owner_auth() -> tuple[dict[str, str], SimpleNamespace]:
    return await _auth_for(RoleName.OWNER)


@pytest.fixture
async def agent_auth() -> tuple[dict[str, str], SimpleNamespace]:
    return await _auth_for(RoleName.AGENT)


@pytest.mark.asyncio
async def test_list_users_includes_role(
    api_client: AsyncClient, manager_auth: tuple[dict[str, str], SimpleNamespace]
) -> None:
    headers, _ = manager_auth
    r = await api_client.get("/api/v1/users", headers=headers)
    assert r.status_code == 200
    users = r.json()
    assert len(users) >= 1
    assert "role" in users[0]
    assert "name" in users[0]["role"]


@pytest.mark.asyncio
async def test_manager_creates_agent_but_not_owner(
    api_client: AsyncClient, manager_auth: tuple[dict[str, str], SimpleNamespace]
) -> None:
    headers, _ = manager_auth
    suffix = uuid.uuid4().hex[:8]
    ok = await api_client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": f"new.agent.{suffix}@example.com",
            "full_name": "New Agent",
            "role": "AGENT",
            "password": "tempPass123!",
        },
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["role"]["name"] == "AGENT"

    forbidden = await api_client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": f"new.owner.{suffix}@example.com",
            "full_name": "New Owner",
            "role": "OWNER",
            "password": "tempPass123!",
        },
    )
    assert forbidden.status_code == 403

    await api_client.patch(
        f"/api/v1/users/{ok.json()['id']}",
        headers=headers,
        json={"is_active": False},
    )


@pytest.mark.asyncio
async def test_admin_creates_manager_and_changes_role(
    api_client: AsyncClient, admin_auth: tuple[dict[str, str], SimpleNamespace]
) -> None:
    headers, admin = admin_auth
    suffix = uuid.uuid4().hex[:8]
    created = await api_client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": f"temp.mgr.{suffix}@example.com",
            "full_name": "Temp Manager",
            "role": "MANAGER",
            "password": "tempPass123!",
        },
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    patched = await api_client.patch(
        f"/api/v1/users/{user_id}",
        headers=headers,
        json={"role": "AGENT", "full_name": "Temp Agent"},
    )
    assert patched.status_code == 200
    assert patched.json()["role"]["name"] == "AGENT"
    assert patched.json()["full_name"] == "Temp Agent"

    async with AsyncSessionLocal() as session:
        audit = await session.scalar(
            select(AuditLog)
            .where(AuditLog.entity_id == user_id, AuditLog.action == "user.role_changed")
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
        assert audit is not None
        assert audit.actor_id == admin.id

    await api_client.patch(f"/api/v1/users/{user_id}", headers=headers, json={"is_active": False})


@pytest.mark.asyncio
async def test_duplicate_email_409(
    api_client: AsyncClient, manager_auth: tuple[dict[str, str], SimpleNamespace]
) -> None:
    headers, _ = manager_auth
    r = await api_client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": "agent@example.com",
            "full_name": "Dup",
            "role": "AGENT",
            "password": "tempPass123!",
        },
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_cannot_deactivate_self(
    api_client: AsyncClient, manager_auth: tuple[dict[str, str], SimpleNamespace]
) -> None:
    headers, manager = manager_auth
    r = await api_client.patch(
        f"/api/v1/users/{manager.id}",
        headers=headers,
        json={"is_active": False},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_cannot_demote_last_owner(
    api_client: AsyncClient, owner_auth: tuple[dict[str, str], SimpleNamespace]
) -> None:
    headers, owner = owner_auth
    r = await api_client.patch(
        f"/api/v1/users/{owner.id}",
        headers=headers,
        json={"role": "ADMIN"},
    )
    assert r.status_code == 409
    assert "last active owner" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_agent_cannot_create_users(
    api_client: AsyncClient, agent_auth: tuple[dict[str, str], SimpleNamespace]
) -> None:
    headers, _ = agent_auth
    r = await api_client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": f"nope.{uuid.uuid4().hex[:6]}@example.com",
            "full_name": "Nope",
            "role": "AGENT",
            "password": "tempPass123!",
        },
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_inactive_user_cannot_login(
    api_client: AsyncClient, admin_auth: tuple[dict[str, str], SimpleNamespace]
) -> None:
    headers, _ = admin_auth
    suffix = uuid.uuid4().hex[:8]
    email = f"inactive.{suffix}@example.com"
    password = "tempPass123!"
    created = await api_client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": email,
            "full_name": "Soon Inactive",
            "role": "AGENT",
            "password": password,
        },
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    deact = await api_client.patch(
        f"/api/v1/users/{user_id}",
        headers=headers,
        json={"is_active": False},
    )
    assert deact.status_code == 200

    login = await api_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 401


@pytest.mark.asyncio
async def test_reset_password(
    api_client: AsyncClient, manager_auth: tuple[dict[str, str], SimpleNamespace]
) -> None:
    headers, _ = manager_auth
    suffix = uuid.uuid4().hex[:8]
    email = f"resetme.{suffix}@example.com"
    created = await api_client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": email,
            "full_name": "Reset Me",
            "role": "AGENT",
            "password": "oldPass123!",
        },
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    reset = await api_client.post(
        f"/api/v1/users/{user_id}/reset-password",
        headers=headers,
        json={"password": "newPass456!"},
    )
    assert reset.status_code == 204

    login = await api_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "newPass456!"},
    )
    assert login.status_code == 200

    await api_client.patch(f"/api/v1/users/{user_id}", headers=headers, json={"is_active": False})
