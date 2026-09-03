"""Notification API and ticket team-scope tests."""

import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.infrastructure.database.models import (
    ChannelType,
    Conversation,
    Customer,
    Priority,
    Role,
    RoleName,
    Team,
    TeamMember,
    Ticket,
    TicketStatus,
    User,
)
from app.infrastructure.database.session import AsyncSessionLocal
from app.main import app
from app.modules.auth.security import create_access_token
from app.modules.notifications.application.service import NotificationService
from app.modules.notifications.domain.models import Notification


@pytest.fixture
async def api_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _auth_for(role_name: RoleName, *, email: str | None = None) -> tuple[dict[str, str], SimpleNamespace]:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(User)
            .join(Role, Role.id == User.role_id)
            .where(Role.name == role_name, User.is_active.is_(True))
            .options(selectinload(User.role))
            .limit(1)
        )
        if email:
            stmt = (
                select(User)
                .where(User.email == email)
                .options(selectinload(User.role))
                .limit(1)
            )
        user = (await session.execute(stmt)).scalar_one()
        actor = SimpleNamespace(id=user.id, organization_id=user.organization_id, email=user.email)
        token = create_access_token(user.id, {"organization_id": user.organization_id})
    return {"Authorization": f"Bearer {token}"}, actor


@pytest.mark.asyncio
async def test_notifications_list_and_read_all(api_client: AsyncClient) -> None:
    headers, manager = await _auth_for(RoleName.MANAGER)
    async with AsyncSessionLocal() as session:
        await NotificationService(session).notify(
            user_id=manager.id,
            organization_id=manager.organization_id,
            event_type="MANAGER_ALERT",
            title="Test alert",
            body="Something happened",
            metadata={"conversation_id": str(uuid.uuid4())},
        )
        await session.commit()

    listed = await api_client.get("/api/v1/notifications", headers=headers)
    assert listed.status_code == 200
    items = listed.json()
    assert any(n["title"] == "Test alert" for n in items)
    assert "metadata" in items[0]

    unread_before = sum(1 for n in items if n["read_at"] is None)
    assert unread_before >= 1

    marked = await api_client.post("/api/v1/notifications/read-all", headers=headers)
    assert marked.status_code == 200
    assert marked.json()["marked"] >= 1

    listed2 = await api_client.get("/api/v1/notifications", headers=headers)
    assert all(n["read_at"] is not None for n in listed2.json() if n["title"] == "Test alert")


@pytest.mark.asyncio
async def test_ticket_team_scope_and_acl(api_client: AsyncClient) -> None:
    headers_agent, agent = await _auth_for(RoleName.AGENT, email="jordan.billing@example.com")
    headers_owner, owner = await _auth_for(RoleName.OWNER)

    async with AsyncSessionLocal() as session:
        org_id = agent.organization_id
        support = await session.scalar(select(Team).where(Team.organization_id == org_id, Team.name == "Support"))
        billing = await session.scalar(select(Team).where(Team.organization_id == org_id, Team.name == "Billing"))
        assert support and billing
        customer = Customer(organization_id=org_id, name=f"Scope {uuid.uuid4().hex[:6]}")
        session.add(customer)
        await session.flush()
        conv = Conversation(
            organization_id=org_id,
            customer_id=customer.id,
            channel=ChannelType.WEB_CHAT,
            assigned_team_id=support.id,
        )
        session.add(conv)
        await session.flush()
        support_ticket = Ticket(
            organization_id=org_id,
            conversation_id=conv.id,
            customer_id=customer.id,
            status=TicketStatus.OPEN,
            priority=Priority.NORMAL,
            assigned_team_id=support.id,
            title="Support only",
        )
        billing_ticket = Ticket(
            organization_id=org_id,
            conversation_id=conv.id,
            customer_id=customer.id,
            status=TicketStatus.OPEN,
            priority=Priority.NORMAL,
            assigned_team_id=billing.id,
            title="Billing only",
        )
        session.add_all([support_ticket, billing_ticket])
        await session.commit()
        support_id, billing_id = support_ticket.id, billing_ticket.id

    # Billing-only agent: team view includes billing, excludes support-only
    team_list = await api_client.get("/api/v1/tickets?view=team", headers=headers_agent)
    assert team_list.status_code == 200
    ids = {t["id"] for t in team_list.json()}
    assert billing_id in ids
    assert support_id not in ids

    # Cannot open other team's ticket
    forbidden = await api_client.get(f"/api/v1/tickets/{support_id}", headers=headers_agent)
    assert forbidden.status_code == 403

    # Can open own team ticket
    allowed = await api_client.get(f"/api/v1/tickets/{billing_id}", headers=headers_agent)
    assert allowed.status_code == 200

    # Agent cannot request all
    all_denied = await api_client.get("/api/v1/tickets?view=all", headers=headers_agent)
    assert all_denied.status_code == 403

    # Owner sees all
    all_ok = await api_client.get("/api/v1/tickets?view=all", headers=headers_owner)
    assert all_ok.status_code == 200
    owner_ids = {t["id"] for t in all_ok.json()}
    assert support_id in owner_ids and billing_id in owner_ids


@pytest.mark.asyncio
async def test_multi_team_agent_sees_union(api_client: AsyncClient) -> None:
    headers, agent = await _auth_for(RoleName.AGENT, email="agent@example.com")
    async with AsyncSessionLocal() as session:
        org_id = agent.organization_id
        support = await session.scalar(select(Team).where(Team.organization_id == org_id, Team.name == "Support"))
        billing = await session.scalar(select(Team).where(Team.organization_id == org_id, Team.name == "Billing"))
        memberships = list(
            (
                await session.execute(select(TeamMember.team_id).where(TeamMember.user_id == agent.id))
            )
            .scalars()
            .all()
        )
        assert support.id in memberships and billing.id in memberships

        customer = Customer(organization_id=org_id, name=f"Multi {uuid.uuid4().hex[:6]}")
        session.add(customer)
        await session.flush()
        conv = Conversation(
            organization_id=org_id,
            customer_id=customer.id,
            channel=ChannelType.WEB_CHAT,
        )
        session.add(conv)
        await session.flush()
        t_support = Ticket(
            organization_id=org_id,
            conversation_id=conv.id,
            customer_id=customer.id,
            status=TicketStatus.OPEN,
            priority=Priority.NORMAL,
            assigned_team_id=support.id,
            title="S",
        )
        t_billing = Ticket(
            organization_id=org_id,
            conversation_id=conv.id,
            customer_id=customer.id,
            status=TicketStatus.OPEN,
            priority=Priority.NORMAL,
            assigned_team_id=billing.id,
            title="B",
        )
        session.add_all([t_support, t_billing])
        await session.commit()
        s_id, b_id = t_support.id, t_billing.id

    r = await api_client.get("/api/v1/tickets?view=team", headers=headers)
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert s_id in ids and b_id in ids


@pytest.mark.asyncio
async def test_escalation_sets_conversation_team() -> None:
    from app.modules.ai.application.escalation_service import EscalationService
    from app.modules.ai.domain.schemas import IntentLabel, SupportAgentState
    from app.modules.conversations.schemas import ConversationCreate
    from app.modules.conversations.service import ConversationService
    from app.infrastructure.database.models import Organization

    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        billing = await session.scalar(select(Team).where(Team.organization_id == org_id, Team.name == "Billing"))
        assert billing is not None
        customer = Customer(organization_id=org_id, name=f"Esc {uuid.uuid4().hex[:6]}")
        session.add(customer)
        await session.flush()
        user = (await session.execute(select(User).limit(1))).scalar_one()
        conv = await ConversationService(session).create_conversation(
            user,
            ConversationCreate(customer_id=customer.id, channel="WEB_CHAT"),
        )
        assert conv.assigned_team_id is None
        state = SupportAgentState(
            conversation_id=conv.id,
            organization_id=org_id,
            user_message="Billing dispute please",
            intent=IntentLabel.BILLING,
            support_confidence=0.2,
            escalation_reason="test",
        )
        ticket = await EscalationService(session).create_from_ai_run(
            state,
            organization_id=org_id,
            ai_run_id=str(uuid.uuid4()),
            intent_team_map={"BILLING": "Billing"},
            notify_customer=False,
        )
        await session.commit()
        refreshed = await session.get(Conversation, conv.id)
        assert ticket.assigned_team_id == billing.id
        assert refreshed is not None
        assert refreshed.assigned_team_id == billing.id
