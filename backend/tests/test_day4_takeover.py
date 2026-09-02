"""Day 4 takeover and angry customer escalation tests."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import (
    AIControlMode,
    Customer,
    Message,
    Organization,
    Priority,
    SenderType,
    Ticket,
    User,
)
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.ai.application.ai_config_service import get_or_create_ai_config
from app.modules.ai.application.ai_service import AIService
from app.modules.ai.application.escalation_service import EscalationService
from app.modules.ai.application.runtime_config import RuntimeAIConfig
from app.modules.ai.domain.models import AIMode
from app.modules.ai.domain.schemas import AgentDecision, SupportAgentState
from app.modules.ai.graphs.support_agent import timed_support_agent
from app.modules.ai.infrastructure.llm.providers import EchoLLMProvider
from app.modules.conversations.schemas import ConversationCreate
from app.modules.conversations.service import ConversationService


@pytest.mark.asyncio
async def test_takeover_blocks_ai_reply() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        user = (await session.execute(select(User).limit(1))).scalar_one()
        customer = Customer(organization_id=org_id, name="Takeover Block")
        session.add(customer)
        await session.flush()
        conv = await ConversationService(session).create_conversation(
            user, ConversationCreate(customer_id=customer.id, channel="WEB_CHAT")
        )
        await ConversationService(session).takeover(user, conv.id)
        msg = Message(
            conversation_id=conv.id,
            sender_type=SenderType.CUSTOMER,
            content="How do I reset my password?",
        )
        session.add(msg)
        await session.flush()

        run = await AIService(session, llm=EchoLLMProvider()).process_customer_message(msg.id)
        assert run is None
        ai_msgs = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == conv.id,
                    Message.sender_type == SenderType.AI,
                )
            )
        ).scalars().all()
        assert len(ai_msgs) == 0
        await session.rollback()


@pytest.mark.asyncio
async def test_angry_customer_escalates_with_high_priority() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        base = await get_or_create_ai_config(session, org_id)
        config = RuntimeAIConfig.from_config(base)
        state = SupportAgentState(
            organization_id=org_id,
            user_message="This is the third time I've contacted you!",
        )
        final, _, _ = await timed_support_agent(
            state, config=config, llm=EchoLLMProvider(), db_session=session
        )
        assert final.sentiment == "ANGRY"
        assert final.decision == AgentDecision.ESCALATE

        user = (await session.execute(select(User).limit(1))).scalar_one()
        customer = Customer(organization_id=org_id, name="Angry Customer")
        session.add(customer)
        await session.flush()
        conv = await ConversationService(session).create_conversation(
            user, ConversationCreate(customer_id=customer.id, channel="WEB_CHAT")
        )
        msg = Message(
            conversation_id=conv.id,
            sender_type=SenderType.CUSTOMER,
            content="This is the third time I've contacted you!",
        )
        session.add(msg)
        await session.flush()

        base.mode = AIMode.AUTO_REPLY
        await AIService(session, llm=EchoLLMProvider()).run_support_agent(
            conv.id, msg.id, persist_side_effects=True
        )
        ticket = await session.scalar(select(Ticket).where(Ticket.conversation_id == conv.id))
        assert ticket is not None
        assert ticket.priority == Priority.HIGH
        assert "AI HANDOFF" in (ticket.description or "")
        await session.rollback()


@pytest.mark.asyncio
async def test_handoff_package_includes_sentiment() -> None:
    state = SupportAgentState(
        user_message="I'm furious!",
        sentiment="ANGRY",
        escalation_reason="Customer sentiment: ANGRY",
        support_confidence=0.5,
    )
    package = EscalationService(None).build_handoff_package(state, None)  # type: ignore[arg-type]
    assert package.sentiment == "ANGRY"
