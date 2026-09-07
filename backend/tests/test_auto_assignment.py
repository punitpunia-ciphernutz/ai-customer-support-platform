"""Team-scoped auto-assignment: ONLINE round-robin on human-need paths."""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from app.infrastructure.database.models import (
    AIControlMode,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    Organization,
    Team,
    TeamMember,
    User,
)
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.ai.application.escalation_service import EscalationService
from app.modules.ai.application.missed_chat_service import MissedChatService
from app.modules.ai.domain.models import AgentAvailability, AgentStatus
from app.modules.ai.domain.schemas import IntentLabel, SupportAgentState
from app.modules.assignment.application.service import AssignmentService
from app.modules.conversations.schemas import ConversationCreate
from app.modules.conversations.service import ConversationService


async def _ensure_member(session, team_id: str, user_id: str) -> None:
    existing = await session.scalar(
        select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
    )
    if existing is None:
        session.add(TeamMember(team_id=team_id, user_id=user_id))


async def _set_availability(
    session,
    *,
    user_id: str,
    organization_id: str,
    status: AgentStatus,
    active_conversation_count: int = 0,
) -> None:
    avail = await session.scalar(select(AgentAvailability).where(AgentAvailability.user_id == user_id))
    if avail is None:
        session.add(
            AgentAvailability(
                user_id=user_id,
                organization_id=organization_id,
                status=status,
                is_online=status == AgentStatus.ONLINE,
                active_conversation_count=active_conversation_count,
            )
        )
    else:
        avail.status = status
        avail.is_online = status == AgentStatus.ONLINE
        avail.active_conversation_count = active_conversation_count


async def _offline_all_team_members(session, team_id: str, organization_id: str) -> None:
    member_ids = list(
        (await session.execute(select(TeamMember.user_id).where(TeamMember.team_id == team_id))).scalars()
    )
    for uid in member_ids:
        await _set_availability(session, user_id=uid, organization_id=organization_id, status=AgentStatus.OFFLINE)


async def _isolate_online_members(
    session,
    *,
    team: Team,
    organization_id: str,
    online_user_ids: list[str],
) -> list[str]:
    """Make only the given users ONLINE members of the team; everyone else on team OFFLINE."""
    for uid in online_user_ids:
        await _ensure_member(session, team.id, uid)
    await _offline_all_team_members(session, team.id, organization_id)
    for uid in online_user_ids:
        await _set_availability(session, user_id=uid, organization_id=organization_id, status=AgentStatus.ONLINE)
    team.last_assigned_user_id = None
    await session.flush()
    return sorted(online_user_ids)


@pytest.mark.asyncio
async def test_create_conversation_defaults_support_without_user() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        user = (await session.execute(select(User).where(User.organization_id == org_id).limit(1))).scalar_one()
        support = await session.scalar(
            select(Team).where(Team.organization_id == org_id, Team.name == "Support")
        )
        assert support is not None
        customer = Customer(organization_id=org_id, name="Create No Assign")
        session.add(customer)
        await session.flush()
        conv = await ConversationService(session).create_conversation(
            user, ConversationCreate(customer_id=customer.id, channel="WEB_CHAT")
        )
        assert conv.assigned_team_id == support.id
        assert conv.assigned_user_id is None
        await session.rollback()


@pytest.mark.asyncio
async def test_round_robin_rotates_online_members_on_same_team() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        team = await session.scalar(select(Team).where(Team.organization_id == org_id, Team.name == "Support"))
        assert team is not None
        users = list(
            (await session.execute(select(User).where(User.organization_id == org_id).limit(3))).scalars()
        )
        assert len(users) >= 3
        ordered = await _isolate_online_members(
            session, team=team, organization_id=org_id, online_user_ids=[u.id for u in users]
        )

        customer = Customer(organization_id=org_id, name="RR Rotate")
        session.add(customer)
        await session.flush()
        svc = AssignmentService(session)
        assigned: list[str] = []
        for _ in range(6):
            conv = Conversation(
                organization_id=org_id,
                customer_id=customer.id,
                channel=ChannelType.WEB_CHAT,
                assigned_team_id=team.id,
            )
            session.add(conv)
            await session.flush()
            agent_id = await svc.assign_round_robin(conv.id, org_id, team.id)
            assert agent_id is not None
            assigned.append(agent_id)
            # Clear user so next RR is independent of prior assignee; cursor stays on team.
            conv.assigned_user_id = None
            await session.flush()

        assert assigned == ordered + ordered
        await session.rollback()


@pytest.mark.asyncio
async def test_auto_assign_skips_away_and_offline() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        team = await session.scalar(select(Team).where(Team.organization_id == org_id, Team.name == "Support"))
        assert team is not None
        users = list(
            (await session.execute(select(User).where(User.organization_id == org_id).limit(2))).scalars()
        )
        assert len(users) >= 2
        await _ensure_member(session, team.id, users[0].id)
        await _ensure_member(session, team.id, users[1].id)
        await _offline_all_team_members(session, team.id, org_id)
        await _set_availability(session, user_id=users[0].id, organization_id=org_id, status=AgentStatus.AWAY)
        await _set_availability(session, user_id=users[1].id, organization_id=org_id, status=AgentStatus.OFFLINE)
        team.last_assigned_user_id = None
        await session.flush()

        customer = Customer(organization_id=org_id, name="Away Offline")
        session.add(customer)
        await session.flush()
        conv = Conversation(
            organization_id=org_id,
            customer_id=customer.id,
            channel=ChannelType.WEB_CHAT,
            assigned_team_id=team.id,
        )
        session.add(conv)
        await session.flush()

        agent_id = await AssignmentService(session).auto_assign_if_needed(conv.id, org_id)
        assert agent_id is None
        await session.refresh(conv)
        assert conv.assigned_team_id == team.id
        assert conv.assigned_user_id is None
        await session.rollback()


@pytest.mark.asyncio
async def test_billing_conversation_not_assigned_to_support_member() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        billing = await session.scalar(
            select(Team).where(Team.organization_id == org_id, Team.name == "Billing")
        )
        support = await session.scalar(
            select(Team).where(Team.organization_id == org_id, Team.name == "Support")
        )
        assert billing is not None and support is not None
        users = list(
            (await session.execute(select(User).where(User.organization_id == org_id).limit(2))).scalars()
        )
        assert len(users) >= 2
        support_agent, billing_agent = users[0], users[1]

        await session.execute(
            delete(TeamMember).where(TeamMember.user_id.in_([support_agent.id, billing_agent.id]))
        )
        await _ensure_member(session, support.id, support_agent.id)
        await _ensure_member(session, billing.id, billing_agent.id)
        await _offline_all_team_members(session, support.id, org_id)
        await _offline_all_team_members(session, billing.id, org_id)
        await _set_availability(
            session, user_id=support_agent.id, organization_id=org_id, status=AgentStatus.ONLINE
        )
        await _set_availability(
            session, user_id=billing_agent.id, organization_id=org_id, status=AgentStatus.ONLINE
        )
        billing.last_assigned_user_id = None
        support.last_assigned_user_id = None
        await session.flush()

        customer = Customer(organization_id=org_id, name="Billing Only")
        session.add(customer)
        await session.flush()
        conv = Conversation(
            organization_id=org_id,
            customer_id=customer.id,
            channel=ChannelType.WEB_CHAT,
            assigned_team_id=billing.id,
        )
        session.add(conv)
        await session.flush()

        agent_id = await AssignmentService(session).auto_assign_if_needed(conv.id, org_id)
        assert agent_id == billing_agent.id
        await session.refresh(conv)
        assert conv.assigned_user_id == billing_agent.id
        assert conv.assigned_team_id == billing.id
        await session.rollback()


@pytest.mark.asyncio
async def test_escalation_auto_assigns_and_mirrors_ticket() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        support = await session.scalar(
            select(Team).where(Team.organization_id == org_id, Team.name == "Support")
        )
        assert support is not None
        user = (await session.execute(select(User).where(User.organization_id == org_id).limit(1))).scalar_one()
        await _isolate_online_members(session, team=support, organization_id=org_id, online_user_ids=[user.id])

        customer = Customer(organization_id=org_id, name="Escalation Assign")
        session.add(customer)
        await session.flush()
        conv = await ConversationService(session).create_conversation(
            user, ConversationCreate(customer_id=customer.id, channel="WEB_CHAT")
        )
        assert conv.assigned_user_id is None

        ticket = await EscalationService(session).create_from_ai_run(
            SupportAgentState(
                conversation_id=conv.id,
                organization_id=org_id,
                user_message="Need a human",
                intent=IntentLabel.GENERAL_QUESTION,
                support_confidence=0.2,
                escalation_reason="test",
            ),
            organization_id=org_id,
            ai_run_id="auto-assign-esc",
            intent_team_map={},
            notify_customer=False,
        )
        await session.refresh(conv)
        assert conv.assigned_user_id == user.id
        assert ticket.assigned_user_id == user.id
        assert ticket.assigned_team_id == support.id
        await session.rollback()


@pytest.mark.asyncio
async def test_escalation_billing_team_picks_billing_member() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        billing = await session.scalar(
            select(Team).where(Team.organization_id == org_id, Team.name == "Billing")
        )
        support = await session.scalar(
            select(Team).where(Team.organization_id == org_id, Team.name == "Support")
        )
        assert billing is not None and support is not None
        users = list(
            (await session.execute(select(User).where(User.organization_id == org_id).limit(2))).scalars()
        )
        support_agent, billing_agent = users[0], users[1]
        await session.execute(
            delete(TeamMember).where(TeamMember.user_id.in_([support_agent.id, billing_agent.id]))
        )
        await _ensure_member(session, support.id, support_agent.id)
        await _ensure_member(session, billing.id, billing_agent.id)
        await _offline_all_team_members(session, support.id, org_id)
        await _offline_all_team_members(session, billing.id, org_id)
        await _set_availability(
            session, user_id=support_agent.id, organization_id=org_id, status=AgentStatus.ONLINE
        )
        await _set_availability(
            session, user_id=billing_agent.id, organization_id=org_id, status=AgentStatus.ONLINE
        )
        billing.last_assigned_user_id = None
        await session.flush()

        customer = Customer(organization_id=org_id, name="Escalation Billing")
        session.add(customer)
        await session.flush()
        conv = await ConversationService(session).create_conversation(
            support_agent, ConversationCreate(customer_id=customer.id, channel="WEB_CHAT")
        )
        assert conv.assigned_team_id == support.id

        ticket = await EscalationService(session).create_from_ai_run(
            SupportAgentState(
                conversation_id=conv.id,
                organization_id=org_id,
                user_message="Billing question",
                intent=IntentLabel.GENERAL_QUESTION,
                support_confidence=0.2,
                escalation_reason="test",
            ),
            organization_id=org_id,
            ai_run_id="auto-assign-billing",
            intent_team_map={"GENERAL_QUESTION": "Billing"},
            notify_customer=False,
        )
        await session.refresh(conv)
        assert conv.assigned_team_id == billing.id
        assert conv.assigned_user_id == billing_agent.id
        assert ticket.assigned_user_id == billing_agent.id
        assert ticket.assigned_user_id != support_agent.id
        await session.rollback()


@pytest.mark.asyncio
async def test_auto_assign_does_not_overwrite_existing_assignee() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        support = await session.scalar(
            select(Team).where(Team.organization_id == org_id, Team.name == "Support")
        )
        assert support is not None
        users = list(
            (await session.execute(select(User).where(User.organization_id == org_id).limit(2))).scalars()
        )
        a, b = users[0], users[1]
        await _isolate_online_members(
            session, team=support, organization_id=org_id, online_user_ids=[a.id, b.id]
        )

        customer = Customer(organization_id=org_id, name="No Overwrite")
        session.add(customer)
        await session.flush()
        conv = Conversation(
            organization_id=org_id,
            customer_id=customer.id,
            channel=ChannelType.WEB_CHAT,
            assigned_team_id=support.id,
            assigned_user_id=a.id,
        )
        session.add(conv)
        await session.flush()

        result = await AssignmentService(session).auto_assign_if_needed(conv.id, org_id)
        assert result == a.id
        await session.refresh(conv)
        assert conv.assigned_user_id == a.id
        await session.rollback()


@pytest.mark.asyncio
async def test_ai_disabled_assigns_online_on_team() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        support = await session.scalar(
            select(Team).where(Team.organization_id == org_id, Team.name == "Support")
        )
        assert support is not None
        user = (await session.execute(select(User).where(User.organization_id == org_id).limit(1))).scalar_one()
        await _isolate_online_members(session, team=support, organization_id=org_id, online_user_ids=[user.id])

        customer = Customer(organization_id=org_id, name="AI Off Online")
        session.add(customer)
        await session.flush()
        conv = Conversation(
            organization_id=org_id,
            customer_id=customer.id,
            channel=ChannelType.WEB_CHAT,
            assigned_team_id=support.id,
            status=ConversationStatus.OPEN,
        )
        session.add(conv)
        await session.flush()

        await MissedChatService(session).route_incoming_if_ai_disabled(conv.id, org_id)
        await session.refresh(conv)
        assert conv.assigned_user_id == user.id
        assert conv.status != ConversationStatus.WAITING_FOR_AGENT
        await session.rollback()


@pytest.mark.asyncio
async def test_ai_disabled_waiting_when_no_online_on_team() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        support = await session.scalar(
            select(Team).where(Team.organization_id == org_id, Team.name == "Support")
        )
        assert support is not None
        await _offline_all_team_members(session, support.id, org_id)
        await session.flush()

        customer = Customer(organization_id=org_id, name="AI Off Offline")
        session.add(customer)
        await session.flush()
        conv = Conversation(
            organization_id=org_id,
            customer_id=customer.id,
            channel=ChannelType.WEB_CHAT,
            assigned_team_id=support.id,
            status=ConversationStatus.OPEN,
        )
        session.add(conv)
        await session.flush()

        await MissedChatService(session).route_incoming_if_ai_disabled(conv.id, org_id)
        await session.refresh(conv)
        assert conv.assigned_user_id is None
        assert conv.status == ConversationStatus.WAITING_FOR_AGENT
        await session.rollback()


@pytest.mark.asyncio
async def test_takeover_assigns_actor_when_unassigned() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        user = (await session.execute(select(User).where(User.organization_id == org_id).limit(1))).scalar_one()
        await _set_availability(session, user_id=user.id, organization_id=org_id, status=AgentStatus.AWAY)
        customer = Customer(organization_id=org_id, name="Takeover Assign")
        session.add(customer)
        await session.flush()
        conv = await ConversationService(session).create_conversation(
            user, ConversationCreate(customer_id=customer.id, channel="WEB_CHAT")
        )
        assert conv.assigned_user_id is None
        updated = await ConversationService(session).takeover(user, conv.id)
        assert updated.ai_control_mode == AIControlMode.HUMAN_CONTROL
        assert updated.assigned_user_id == user.id
        await session.rollback()


@pytest.mark.asyncio
async def test_takeover_does_not_overwrite_existing_assignee() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        users = list(
            (await session.execute(select(User).where(User.organization_id == org_id).limit(2))).scalars()
        )
        a, b = users[0], users[1]
        customer = Customer(organization_id=org_id, name="Takeover Keep")
        session.add(customer)
        await session.flush()
        conv = await ConversationService(session).create_conversation(
            a, ConversationCreate(customer_id=customer.id, channel="WEB_CHAT")
        )
        conv.assigned_user_id = a.id
        await session.flush()
        updated = await ConversationService(session).takeover(b, conv.id)
        assert updated.assigned_user_id == a.id
        assert updated.ai_control_mode == AIControlMode.HUMAN_CONTROL
        await session.rollback()


@pytest.mark.asyncio
async def test_support_ticket_assigns_support_online_member() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        support = await session.scalar(
            select(Team).where(Team.organization_id == org_id, Team.name == "Support")
        )
        assert support is not None
        user = (await session.execute(select(User).where(User.organization_id == org_id).limit(1))).scalar_one()
        await _isolate_online_members(session, team=support, organization_id=org_id, online_user_ids=[user.id])

        customer = Customer(organization_id=org_id, name="Support Ticket RR")
        session.add(customer)
        await session.flush()
        conv = await ConversationService(session).create_conversation(
            user, ConversationCreate(customer_id=customer.id, channel="WEB_CHAT")
        )
        ticket = await EscalationService(session).create_from_ai_run(
            SupportAgentState(
                conversation_id=conv.id,
                organization_id=org_id,
                user_message="Help",
                intent=IntentLabel.GENERAL_QUESTION,
                support_confidence=0.1,
                escalation_reason="test",
            ),
            organization_id=org_id,
            ai_run_id="support-ticket-rr",
            intent_team_map={},
            notify_customer=False,
        )
        await session.refresh(conv)
        assert ticket.assigned_team_id == support.id
        assert ticket.assigned_user_id == user.id
        assert conv.assigned_team_id == support.id
        assert conv.assigned_user_id == user.id
        await session.rollback()


@pytest.mark.asyncio
async def test_transfer_support_to_billing_reassigns_online_billing_member() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        support = await session.scalar(
            select(Team).where(Team.organization_id == org_id, Team.name == "Support")
        )
        billing = await session.scalar(
            select(Team).where(Team.organization_id == org_id, Team.name == "Billing")
        )
        assert support is not None and billing is not None
        users = list(
            (await session.execute(select(User).where(User.organization_id == org_id).limit(2))).scalars()
        )
        support_agent, billing_agent = users[0], users[1]
        await session.execute(
            delete(TeamMember).where(TeamMember.user_id.in_([support_agent.id, billing_agent.id]))
        )
        await _ensure_member(session, support.id, support_agent.id)
        await _ensure_member(session, billing.id, billing_agent.id)
        await _offline_all_team_members(session, support.id, org_id)
        await _offline_all_team_members(session, billing.id, org_id)
        await _set_availability(
            session, user_id=support_agent.id, organization_id=org_id, status=AgentStatus.ONLINE
        )
        await _set_availability(
            session, user_id=billing_agent.id, organization_id=org_id, status=AgentStatus.ONLINE
        )
        support.last_assigned_user_id = None
        billing.last_assigned_user_id = None
        await session.flush()

        customer = Customer(organization_id=org_id, name="Transfer Billing")
        session.add(customer)
        await session.flush()
        conv = await ConversationService(session).create_conversation(
            support_agent, ConversationCreate(customer_id=customer.id, channel="WEB_CHAT")
        )
        ticket = await EscalationService(session).create_from_ai_run(
            SupportAgentState(
                conversation_id=conv.id,
                organization_id=org_id,
                user_message="Support first",
                intent=IntentLabel.GENERAL_QUESTION,
                support_confidence=0.1,
                escalation_reason="test",
            ),
            organization_id=org_id,
            ai_run_id="xfer-support",
            intent_team_map={},
            notify_customer=False,
        )
        await session.refresh(conv)
        assert ticket.assigned_user_id == support_agent.id

        assignee = await AssignmentService(session).ensure_assignee_for_team(
            org_id,
            billing.id,
            conversation_id=conv.id,
            ticket=ticket,
            sync_linked_tickets=True,
        )
        await session.refresh(conv)
        await session.refresh(ticket)
        assert assignee == billing_agent.id
        assert ticket.assigned_team_id == billing.id
        assert ticket.assigned_user_id == billing_agent.id
        assert ticket.assigned_user_id != support_agent.id
        assert conv.assigned_team_id == billing.id
        assert conv.assigned_user_id == billing_agent.id
        await session.rollback()


@pytest.mark.asyncio
async def test_transfer_billing_to_third_team_reassigns() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        billing = await session.scalar(
            select(Team).where(Team.organization_id == org_id, Team.name == "Billing")
        )
        assert billing is not None
        users = list(
            (await session.execute(select(User).where(User.organization_id == org_id).limit(3))).scalars()
        )
        billing_agent, other_agent = users[0], users[1]
        third = Team(organization_id=org_id, name=f"Tier3-{other_agent.id[:8]}")
        session.add(third)
        await session.flush()

        await session.execute(
            delete(TeamMember).where(TeamMember.user_id.in_([billing_agent.id, other_agent.id]))
        )
        await _ensure_member(session, billing.id, billing_agent.id)
        await _ensure_member(session, third.id, other_agent.id)
        await _offline_all_team_members(session, billing.id, org_id)
        await _set_availability(
            session, user_id=billing_agent.id, organization_id=org_id, status=AgentStatus.ONLINE
        )
        await _set_availability(
            session, user_id=other_agent.id, organization_id=org_id, status=AgentStatus.ONLINE
        )
        billing.last_assigned_user_id = None
        third.last_assigned_user_id = None
        await session.flush()

        customer = Customer(organization_id=org_id, name="Transfer Third")
        session.add(customer)
        await session.flush()
        conv = Conversation(
            organization_id=org_id,
            customer_id=customer.id,
            channel=ChannelType.WEB_CHAT,
            assigned_team_id=billing.id,
        )
        session.add(conv)
        await session.flush()
        from app.infrastructure.database.models import Ticket, TicketSource, TicketStatus

        ticket = Ticket(
            organization_id=org_id,
            conversation_id=conv.id,
            customer_id=customer.id,
            source=TicketSource.AUTOMATION,
            title="Billing ticket",
            status=TicketStatus.OPEN,
            assigned_team_id=billing.id,
        )
        session.add(ticket)
        await session.flush()

        await AssignmentService(session).ensure_assignee_for_team(
            org_id, billing.id, conversation_id=conv.id, ticket=ticket
        )
        await session.refresh(ticket)
        assert ticket.assigned_user_id == billing_agent.id

        await AssignmentService(session).ensure_assignee_for_team(
            org_id, third.id, conversation_id=conv.id, ticket=ticket
        )
        await session.refresh(conv)
        await session.refresh(ticket)
        assert ticket.assigned_team_id == third.id
        assert ticket.assigned_user_id == other_agent.id
        assert conv.assigned_user_id == other_agent.id
        await session.rollback()


@pytest.mark.asyncio
async def test_transfer_to_team_with_no_online_leaves_unassigned() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        support = await session.scalar(
            select(Team).where(Team.organization_id == org_id, Team.name == "Support")
        )
        billing = await session.scalar(
            select(Team).where(Team.organization_id == org_id, Team.name == "Billing")
        )
        assert support is not None and billing is not None
        users = list(
            (await session.execute(select(User).where(User.organization_id == org_id).limit(2))).scalars()
        )
        support_agent, billing_agent = users[0], users[1]
        await session.execute(
            delete(TeamMember).where(TeamMember.user_id.in_([support_agent.id, billing_agent.id]))
        )
        await _ensure_member(session, support.id, support_agent.id)
        await _ensure_member(session, billing.id, billing_agent.id)
        await _offline_all_team_members(session, support.id, org_id)
        await _offline_all_team_members(session, billing.id, org_id)
        await _set_availability(
            session, user_id=support_agent.id, organization_id=org_id, status=AgentStatus.ONLINE
        )
        await _set_availability(
            session, user_id=billing_agent.id, organization_id=org_id, status=AgentStatus.OFFLINE
        )
        await session.flush()

        customer = Customer(organization_id=org_id, name="Transfer Offline")
        session.add(customer)
        await session.flush()
        conv = Conversation(
            organization_id=org_id,
            customer_id=customer.id,
            channel=ChannelType.WEB_CHAT,
            assigned_team_id=support.id,
            assigned_user_id=support_agent.id,
        )
        session.add(conv)
        await session.flush()
        from app.infrastructure.database.models import Ticket, TicketSource, TicketStatus

        ticket = Ticket(
            organization_id=org_id,
            conversation_id=conv.id,
            customer_id=customer.id,
            source=TicketSource.AUTOMATION,
            title="Support ticket",
            status=TicketStatus.OPEN,
            assigned_team_id=support.id,
            assigned_user_id=support_agent.id,
        )
        session.add(ticket)
        await session.flush()

        await AssignmentService(session).ensure_assignee_for_team(
            org_id, billing.id, conversation_id=conv.id, ticket=ticket
        )
        await session.refresh(conv)
        await session.refresh(ticket)
        assert ticket.assigned_team_id == billing.id
        assert ticket.assigned_user_id is None
        assert conv.assigned_team_id == billing.id
        assert conv.assigned_user_id is None
        await session.rollback()


@pytest.mark.asyncio
async def test_manual_assignment_preserved_when_assignee_on_new_team() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        support = await session.scalar(
            select(Team).where(Team.organization_id == org_id, Team.name == "Support")
        )
        billing = await session.scalar(
            select(Team).where(Team.organization_id == org_id, Team.name == "Billing")
        )
        assert support is not None and billing is not None
        user = (await session.execute(select(User).where(User.organization_id == org_id).limit(1))).scalar_one()
        await _ensure_member(session, support.id, user.id)
        await _ensure_member(session, billing.id, user.id)
        await _offline_all_team_members(session, support.id, org_id)
        await _offline_all_team_members(session, billing.id, org_id)
        await _set_availability(session, user_id=user.id, organization_id=org_id, status=AgentStatus.ONLINE)
        # Another Online Billing member who would win RR if we reassigned
        other = list(
            (await session.execute(select(User).where(User.organization_id == org_id).limit(2))).scalars()
        )[1]
        await _ensure_member(session, billing.id, other.id)
        await _set_availability(session, user_id=other.id, organization_id=org_id, status=AgentStatus.ONLINE)
        billing.last_assigned_user_id = other.id
        await session.flush()

        customer = Customer(organization_id=org_id, name="Manual Keep")
        session.add(customer)
        await session.flush()
        conv = Conversation(
            organization_id=org_id,
            customer_id=customer.id,
            channel=ChannelType.WEB_CHAT,
            assigned_team_id=support.id,
            assigned_user_id=user.id,
        )
        session.add(conv)
        await session.flush()
        from app.infrastructure.database.models import Ticket, TicketSource, TicketStatus

        ticket = Ticket(
            organization_id=org_id,
            conversation_id=conv.id,
            customer_id=customer.id,
            source=TicketSource.AUTOMATION,
            title="Keep assignee",
            status=TicketStatus.OPEN,
            assigned_team_id=support.id,
            assigned_user_id=user.id,
        )
        session.add(ticket)
        await session.flush()

        await AssignmentService(session).ensure_assignee_for_team(
            org_id, billing.id, conversation_id=conv.id, ticket=ticket, keep_assignee_if_member=True
        )
        await session.refresh(ticket)
        assert ticket.assigned_team_id == billing.id
        assert ticket.assigned_user_id == user.id
        await session.rollback()


@pytest.mark.asyncio
async def test_manual_sync_assignment_sets_explicit_user() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        support = await session.scalar(
            select(Team).where(Team.organization_id == org_id, Team.name == "Support")
        )
        assert support is not None
        users = list(
            (await session.execute(select(User).where(User.organization_id == org_id).limit(2))).scalars()
        )
        a, b = users[0], users[1]
        customer = Customer(organization_id=org_id, name="Manual Sync")
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
        from app.infrastructure.database.models import Ticket, TicketSource, TicketStatus

        ticket = Ticket(
            organization_id=org_id,
            conversation_id=conv.id,
            customer_id=customer.id,
            source=TicketSource.AUTOMATION,
            title="Manual",
            status=TicketStatus.OPEN,
            assigned_team_id=support.id,
        )
        session.add(ticket)
        await session.flush()

        await AssignmentService(session).sync_manual_assignment(
            org_id,
            conversation_id=conv.id,
            assigned_team_id=support.id,
            assigned_user_id=b.id,
            ticket=ticket,
        )
        await session.refresh(conv)
        await session.refresh(ticket)
        assert conv.assigned_user_id == b.id
        assert ticket.assigned_user_id == b.id
        assert a.id != b.id
        await session.rollback()
