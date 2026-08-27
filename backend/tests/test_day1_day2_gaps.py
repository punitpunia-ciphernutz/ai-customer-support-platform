"""RBAC negative tests, audit rows, no-auto-reply, websocket auth."""

import os
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import select

from app.infrastructure.database.models import AuditLog, Message, Organization, Role, RoleName, User
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.ai.application.ai_service import AIService
from app.modules.ai.infrastructure.llm.providers import EchoLLMProvider
from app.modules.auth.permissions import ROLE_PERMISSIONS
from app.modules.auth.security import create_access_token, hash_password
from app.modules.inbox import ws as ws_module

BASE = os.getenv("API_BASE", "http://localhost:8000/api/v1")
EMAIL = os.getenv("SEED_AGENT_EMAIL", "agent@example.com")
PASSWORD = os.getenv("SEED_AGENT_PASSWORD", "agent123!")


@pytest.fixture(scope="module")
def agent_token() -> str:
    r = httpx.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"API not available: {r.status_code}")
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_readonly_cannot_write_knowledge() -> None:
    import uuid

    email = f"readonly-{uuid.uuid4().hex[:8]}@example.com"
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        role = (
            await session.execute(select(Role).where(Role.name == RoleName.READ_ONLY))
        ).scalar_one()
        role.permissions = list(ROLE_PERMISSIONS[RoleName.READ_ONLY])
        user = User(
            organization_id=org_id,
            role_id=role.id,
            email=email,
            full_name="Read Only",
            hashed_password=hash_password("readonly123!"),
            is_active=True,
        )
        session.add(user)
        await session.flush()
        token = create_access_token(user.id, extra={"org_id": org_id, "email": user.email})
        await session.commit()

    try:
        r = httpx.post(
            f"{BASE}/knowledge/sources",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Should Fail", "type": "TEXT"},
            timeout=30,
        )
    except httpx.ConnectError:
        pytest.skip("API not available")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_assign_and_close_write_audit(agent_token: str) -> None:
    h = {"Authorization": f"Bearer {agent_token}"}
    c = httpx.post(
        f"{BASE}/customers",
        headers=h,
        json={"name": "Audit Customer", "email": "audit.customer@example.com"},
        timeout=30,
    )
    if c.status_code != 201:
        pytest.skip(f"API unavailable: {c.status_code}")
    customer_id = c.json()["id"]
    me = httpx.get(f"{BASE}/auth/me", headers=h, timeout=30).json()
    conv = httpx.post(
        f"{BASE}/conversations",
        headers=h,
        json={"customer_id": customer_id, "channel": "WEB_CHAT", "initial_message": "Hi"},
        timeout=30,
    )
    assert conv.status_code == 201
    conversation_id = conv.json()["id"]

    assigned = httpx.patch(
        f"{BASE}/conversations/{conversation_id}",
        headers=h,
        json={"assigned_user_id": me["id"]},
        timeout=30,
    )
    assert assigned.status_code == 200
    closed = httpx.patch(
        f"{BASE}/conversations/{conversation_id}",
        headers=h,
        json={"status": "CLOSED"},
        timeout=30,
    )
    assert closed.status_code == 200

    async with AsyncSessionLocal() as session:
        actions = (
            await session.execute(
                select(AuditLog.action).where(AuditLog.entity_id == conversation_id)
            )
        ).scalars().all()
        assert "conversation.assigned" in actions
        assert "conversation.closed" in actions


@pytest.mark.asyncio
async def test_classify_does_not_create_message_or_auto_reply() -> None:
    async with AsyncSessionLocal() as session:
        before = (await session.execute(select(Message.id))).scalars().all()
        before_set = set(before)
        classification, run = await AIService(session, llm=EchoLLMProvider()).classify(
            "I cannot log into my account"
        )
        assert classification.intent.value == "ACCOUNT_ACCESS"
        assert run.id
        after = set((await session.execute(select(Message.id))).scalars().all())
        assert after == before_set
        await session.rollback()


@pytest.mark.asyncio
async def test_websocket_agent_requires_token() -> None:
    """Agent /ws closes without a valid token."""
    websocket = AsyncMock()
    websocket.close = AsyncMock()
    websocket.receive_text = AsyncMock(side_effect=Exception("stop"))
    with patch.object(ws_module, "ensure_listener_started"):
        await ws_module.websocket_agent(websocket, token=None)
    websocket.close.assert_awaited()
    code = websocket.close.await_args.args[0] if websocket.close.await_args.args else websocket.close.await_args.kwargs.get("code")
    assert code == 4401
