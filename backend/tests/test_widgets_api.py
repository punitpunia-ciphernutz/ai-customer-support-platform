"""Widget agent CRUD + public session/isolation API tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.infrastructure.database.models import (
    ChannelConfiguration,
    ChannelType,
    ChatWidget,
    Role,
    RoleName,
    User,
    WidgetStatus,
)
from app.infrastructure.database.session import AsyncSessionLocal
from app.main import app
from app.modules.auth.security import create_access_token
from app.modules.widgets.visitor_token import create_visitor_token


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
async def admin_auth() -> tuple[dict[str, str], SimpleNamespace]:
    return await _auth_for(RoleName.ADMIN)


@pytest.mark.asyncio
async def test_widget_crud_generates_public_id(
    api_client: AsyncClient, admin_auth: tuple[dict[str, str], SimpleNamespace]
) -> None:
    headers, _ = admin_auth
    create = await api_client.post(
        "/api/v1/widgets",
        headers=headers,
        json={
            "name": "Marketing Widget",
            "status": "DRAFT",
            "allowed_domains": [],
            "welcome_message": "Hello there",
        },
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["public_id"].startswith("wgt_")
    assert body["status"] == "DRAFT"
    widget_id = body["id"]

    patch = await api_client.patch(
        f"/api/v1/widgets/{widget_id}",
        headers=headers,
        json={"status": "ACTIVE", "allowed_domains": ["example.com"]},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["status"] == "ACTIVE"
    assert patch.json()["allowed_domains"] == ["example.com"]

    snippet = await api_client.get(f"/api/v1/widgets/{widget_id}/embed-snippet", headers=headers)
    assert snippet.status_code == 200
    assert body["public_id"] in snippet.json()["snippet"]

    # cleanup
    await api_client.delete(f"/api/v1/widgets/{widget_id}", headers=headers)


@pytest.mark.asyncio
async def test_active_requires_domain(
    api_client: AsyncClient, admin_auth: tuple[dict[str, str], SimpleNamespace]
) -> None:
    headers, _ = admin_auth
    resp = await api_client.post(
        "/api/v1/widgets",
        headers=headers,
        json={"name": "Bad Active", "status": "ACTIVE", "allowed_domains": []},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_public_session_and_domain_gate(
    api_client: AsyncClient, admin_auth: tuple[dict[str, str], SimpleNamespace]
) -> None:
    headers, actor = admin_auth
    create = await api_client.post(
        "/api/v1/widgets",
        headers=headers,
        json={
            "name": "Public Test Widget",
            "status": "ACTIVE",
            "allowed_domains": ["allowed.example"],
        },
    )
    assert create.status_code == 201, create.text
    public_id = create.json()["public_id"]
    widget_id = create.json()["id"]

    denied = await api_client.get(
        f"/api/v1/public/widgets/{public_id}/config",
        headers={"X-Widget-Page-Host": "evil.com"},
    )
    assert denied.status_code == 403

    ok = await api_client.get(
        f"/api/v1/public/widgets/{public_id}/config",
        headers={"X-Widget-Page-Host": "allowed.example"},
    )
    assert ok.status_code == 200
    assert ok.json()["public_id"] == public_id

    session = await api_client.post(
        f"/api/v1/public/widgets/{public_id}/session",
        headers={"X-Widget-Page-Host": "allowed.example"},
        json={"page_host": "allowed.example"},
    )
    assert session.status_code == 200, session.text
    data = session.json()
    assert data["visitor_token"]
    assert data["customer_id"]
    assert data["visitor_key"]

    conv = await api_client.post(
        f"/api/v1/public/widgets/{public_id}/conversations",
        headers={
            "Authorization": f"Bearer {data['visitor_token']}",
            "X-Widget-Page-Host": "allowed.example",
        },
        json={"content": "Hello from embed"},
    )
    assert conv.status_code == 201, conv.text
    assert conv.json()["channel"] == "WEB_CHAT"
    assert conv.json()["widget_id"] == widget_id
    assert conv.json()["customer_id"] == data["customer_id"]

    # Soft-delete path: inactivate then delete may conflict — just inactivate for cleanup
    await api_client.patch(
        f"/api/v1/widgets/{widget_id}",
        headers=headers,
        json={"status": "INACTIVE"},
    )


@pytest.mark.asyncio
async def test_visitor_isolation_across_widgets(
    api_client: AsyncClient, admin_auth: tuple[dict[str, str], SimpleNamespace]
) -> None:
    headers, _ = admin_auth
    a = await api_client.post(
        "/api/v1/widgets",
        headers=headers,
        json={"name": "Widget A", "status": "ACTIVE", "allowed_domains": ["a.example"]},
    )
    b = await api_client.post(
        "/api/v1/widgets",
        headers=headers,
        json={"name": "Widget B", "status": "ACTIVE", "allowed_domains": ["b.example"]},
    )
    assert a.status_code == 201 and b.status_code == 201
    a_pub, b_pub = a.json()["public_id"], b.json()["public_id"]
    a_id, b_id = a.json()["id"], b.json()["id"]

    sess_a = await api_client.post(
        f"/api/v1/public/widgets/{a_pub}/session",
        headers={"X-Widget-Page-Host": "a.example"},
        json={"page_host": "a.example"},
    )
    assert sess_a.status_code == 200
    token_a = sess_a.json()["visitor_token"]

    conv = await api_client.post(
        f"/api/v1/public/widgets/{a_pub}/conversations",
        headers={"Authorization": f"Bearer {token_a}", "X-Widget-Page-Host": "a.example"},
        json={"content": "secret for A"},
    )
    assert conv.status_code == 201
    conversation_id = conv.json()["id"]

    # Token A cannot read via widget B
    leaked = await api_client.get(
        f"/api/v1/public/widgets/{b_pub}/conversations/{conversation_id}/messages",
        headers={"Authorization": f"Bearer {token_a}", "X-Widget-Page-Host": "b.example"},
    )
    assert leaked.status_code in (401, 404)

    await api_client.patch(f"/api/v1/widgets/{a_id}", headers=headers, json={"status": "INACTIVE"})
    await api_client.patch(f"/api/v1/widgets/{b_id}", headers=headers, json={"status": "INACTIVE"})


@pytest.mark.asyncio
async def test_web_chat_disabled_blocks_embed(
    api_client: AsyncClient, admin_auth: tuple[dict[str, str], SimpleNamespace]
) -> None:
    headers, actor = admin_auth
    create = await api_client.post(
        "/api/v1/widgets",
        headers=headers,
        json={"name": "Gate Widget", "status": "ACTIVE", "allowed_domains": ["gate.example"]},
    )
    assert create.status_code == 201
    public_id = create.json()["public_id"]
    widget_id = create.json()["id"]

    async with AsyncSessionLocal() as session:
        cfg = await session.scalar(
            select(ChannelConfiguration).where(
                ChannelConfiguration.organization_id == actor.organization_id,
                ChannelConfiguration.channel == ChannelType.WEB_CHAT,
            )
        )
        assert cfg is not None
        cfg.enabled = False
        await session.commit()

    try:
        sess = await api_client.post(
            f"/api/v1/public/widgets/{public_id}/session",
            headers={"X-Widget-Page-Host": "gate.example"},
            json={"page_host": "gate.example"},
        )
        assert sess.status_code == 403
    finally:
        async with AsyncSessionLocal() as session:
            cfg = await session.scalar(
                select(ChannelConfiguration).where(
                    ChannelConfiguration.organization_id == actor.organization_id,
                    ChannelConfiguration.channel == ChannelType.WEB_CHAT,
                )
            )
            if cfg is not None:
                cfg.enabled = True
                await session.commit()
        await api_client.patch(
            f"/api/v1/widgets/{widget_id}",
            headers=headers,
            json={"status": "INACTIVE"},
        )


@pytest.mark.asyncio
async def test_visitor_token_typ_required() -> None:
    token, _ = create_visitor_token(
        customer_id="cust",
        organization_id="org",
        widget_id="wid",
        widget_public_id="wgt_x",
    )
    from app.modules.widgets.visitor_token import decode_visitor_token

    payload = decode_visitor_token(token)
    assert payload["typ"] == "visitor"
    assert payload["sub"] == "cust"

    agent = create_access_token("user", {"organization_id": "org"})
    with pytest.raises(ValueError):
        decode_visitor_token(agent)
