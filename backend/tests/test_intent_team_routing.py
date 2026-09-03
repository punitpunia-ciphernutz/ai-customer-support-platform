"""Intent → team map assigns AI escalation tickets without changing automations."""

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import Customer, Organization, Team, User
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.ai.application.escalation_service import EscalationService
from app.modules.ai.domain.schemas import IntentLabel, SupportAgentState
from app.modules.conversations.schemas import ConversationCreate
from app.modules.conversations.service import ConversationService


@pytest.mark.asyncio
async def test_intent_team_map_assigns_escalation_ticket() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        billing = await session.scalar(
            select(Team).where(Team.organization_id == org_id, Team.name == "Billing")
        )
        support = await session.scalar(
            select(Team).where(Team.organization_id == org_id, Team.name == "Support")
        )
        assert billing is not None and support is not None

        customer = Customer(organization_id=org_id, name="Route User", email="route-map@example.com")
        session.add(customer)
        await session.flush()
        user = (await session.execute(select(User).limit(1))).scalar_one()
        conv = await ConversationService(session).create_conversation(
            user,
            ConversationCreate(customer_id=customer.id, channel="WEB_CHAT"),
        )
        state = SupportAgentState(
            conversation_id=conv.id,
            organization_id=org_id,
            user_message="What are your hours?",
            intent=IntentLabel.GENERAL_QUESTION,
            support_confidence=0.4,
            escalation_reason="test",
        )
        esc = EscalationService(session)

        mapped = await esc.create_from_ai_run(
            state,
            organization_id=org_id,
            ai_run_id="intent-map-billing",
            intent_team_map={"GENERAL_QUESTION": "Billing"},
            notify_customer=False,
        )
        assert mapped.assigned_team_id == billing.id

        missing = await esc.create_from_ai_run(
            state,
            organization_id=org_id,
            ai_run_id="intent-map-missing",
            intent_team_map={"GENERAL_QUESTION": "No Such Team"},
            notify_customer=False,
        )
        assert missing.assigned_team_id == support.id

        default = await esc.create_from_ai_run(
            state,
            organization_id=org_id,
            ai_run_id="intent-map-default",
            intent_team_map={},
            notify_customer=False,
        )
        assert default.assigned_team_id == support.id
        await session.rollback()
