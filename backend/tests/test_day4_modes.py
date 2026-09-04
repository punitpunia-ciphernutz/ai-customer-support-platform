"""Day 4 bot mode behavior tests."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import Conversation, Customer, Message, Organization, SenderType, Ticket
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.ai.application.ai_config_service import get_or_create_ai_config
from app.modules.ai.application.ai_service import AIService
from app.modules.ai.application.runtime_config import RuntimeAIConfig
from app.modules.ai.domain.models import AIMode
from app.modules.ai.domain.schemas import AgentDecision, SupportAgentState
from app.modules.ai.graphs.support_agent import timed_support_agent
from app.modules.ai.infrastructure.llm.providers import EchoLLMProvider
from app.modules.knowledge.infrastructure.embeddings.provider import OfflineSemanticEmbeddingProvider


@pytest.fixture(autouse=True)
def offline_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.modules.knowledge.infrastructure.embeddings.provider.get_embedding_provider",
        lambda: OfflineSemanticEmbeddingProvider(),
    )


@pytest.mark.asyncio
async def test_draft_only_sends_when_grounded() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        base = await get_or_create_ai_config(session, org_id)
        base.mode = AIMode.DRAFT_ONLY
        config = RuntimeAIConfig.from_config(base)
        state = SupportAgentState(
            organization_id=org_id,
            user_message="How do I reset my password?",
        )
        final, _, _ = await timed_support_agent(state, config=config, llm=EchoLLMProvider(), db_session=session)
        assert final.decision == AgentDecision.AI_RESOLVE
        assert final.grounded

        customer = Customer(organization_id=org_id, name="KB Mode")
        session.add(customer)
        await session.flush()
        conv = Conversation(organization_id=org_id, customer_id=customer.id, channel="FORM")
        session.add(conv)
        await session.flush()
        msg = Message(
            conversation_id=conv.id,
            sender_type=SenderType.CUSTOMER,
            content="How do I reset my password?",
        )
        session.add(msg)
        await session.flush()

        ai = AIService(session, llm=EchoLLMProvider())
        response, run = await ai.run_support_agent(conv.id, msg.id, persist_side_effects=True)
        assert response.decision == AgentDecision.AI_RESOLVE

        ai_msgs = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == conv.id,
                    Message.sender_type == SenderType.AI,
                )
            )
        ).scalars().all()
        assert len(ai_msgs) == 1
        assert run.trace
        assert len(run.trace) >= 3
        await session.rollback()


@pytest.mark.asyncio
async def test_draft_only_soft_refuses_unknown_without_ticket() -> None:
    """With Response Policy on, OOD soft-replies instead of ticket (DRAFT_ONLY may send soft)."""
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        base = await get_or_create_ai_config(session, org_id)
        base.mode = AIMode.DRAFT_ONLY
        base.response_policy_enabled = True
        config = RuntimeAIConfig.from_config(base)
        final, _, _ = await timed_support_agent(
            SupportAgentState(organization_id=org_id, user_message="Does your product integrate with XYZ?"),
            config=config,
            llm=EchoLLMProvider(),
            db_session=session,
        )
        assert final.decision == AgentDecision.SOFT_REPLY

        customer = Customer(organization_id=org_id, name="KB Soft Refuse")
        session.add(customer)
        await session.flush()
        conv = Conversation(organization_id=org_id, customer_id=customer.id, channel="FORM")
        session.add(conv)
        await session.flush()
        msg = Message(
            conversation_id=conv.id,
            sender_type=SenderType.CUSTOMER,
            content="Does your product integrate with XYZ?",
        )
        session.add(msg)
        await session.flush()

        await AIService(session, llm=EchoLLMProvider()).run_support_agent(
            conv.id, msg.id, persist_side_effects=True
        )
        tickets = (
            await session.execute(select(Ticket).where(Ticket.conversation_id == conv.id))
        ).scalars().all()
        assert len(tickets) == 0
        ai_msgs = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == conv.id,
                    Message.sender_type == SenderType.AI,
                )
            )
        ).scalars().all()
        assert len(ai_msgs) == 1
        await session.rollback()


@pytest.mark.asyncio
async def test_draft_only_escalates_unknown_when_policy_off() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        base = await get_or_create_ai_config(session, org_id)
        base.mode = AIMode.DRAFT_ONLY
        base.response_policy_enabled = False
        config = RuntimeAIConfig.from_config(base)
        final, _, _ = await timed_support_agent(
            SupportAgentState(organization_id=org_id, user_message="Does your product integrate with XYZ?"),
            config=config,
            llm=EchoLLMProvider(),
            db_session=session,
        )
        assert final.decision == AgentDecision.ESCALATE

        customer = Customer(organization_id=org_id, name="KB Escalate")
        session.add(customer)
        await session.flush()
        conv = Conversation(organization_id=org_id, customer_id=customer.id, channel="FORM")
        session.add(conv)
        await session.flush()
        msg = Message(
            conversation_id=conv.id,
            sender_type=SenderType.CUSTOMER,
            content="Does your product integrate with XYZ?",
        )
        session.add(msg)
        await session.flush()

        from app.infrastructure.database.models import Ticket

        await AIService(session, llm=EchoLLMProvider()).run_support_agent(
            conv.id, msg.id, persist_side_effects=True
        )
        tickets = (
            await session.execute(select(Ticket).where(Ticket.conversation_id == conv.id))
        ).scalars().all()
        assert len(tickets) == 1
        ai_msgs = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == conv.id,
                    Message.sender_type == SenderType.AI,
                )
            )
        ).scalars().all()
        assert len(ai_msgs) == 0
        notices = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == conv.id,
                    Message.sender_type == SenderType.SYSTEM,
                )
            )
        ).scalars().all()
        customer_notices = [
            m for m in notices if (m.metadata_ or {}).get("ai_escalation_notice")
        ]
        assert len(customer_notices) == 1
        assert customer_notices[0].metadata_["ticket_id"] == tickets[0].id
        assert "ticket has been created" in customer_notices[0].content.lower()
        await session.rollback()


@pytest.mark.asyncio
async def test_suggest_mode_never_sends_customer_ai_message() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        customer = Customer(organization_id=org_id, name="Suggest Mode")
        session.add(customer)
        await session.flush()
        conv = Conversation(organization_id=org_id, customer_id=customer.id, channel="EMAIL")
        session.add(conv)
        await session.flush()
        msg = Message(
            conversation_id=conv.id,
            sender_type=SenderType.CUSTOMER,
            content="How do I reset my password?",
        )
        session.add(msg)
        await session.flush()

        await AIService(session, llm=EchoLLMProvider()).run_support_agent(
            conv.id, msg.id, persist_side_effects=True
        )
        ai_customer = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == conv.id,
                    Message.sender_type == SenderType.AI,
                )
            )
        ).scalars().all()
        suggestions = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == conv.id,
                    Message.metadata_["suggestion"].astext == "true",
                )
            )
        ).scalars().all()
        assert len(ai_customer) == 0
        assert len(suggestions) == 1
        assert suggestions[0].metadata_["suggestion_status"] == "generated"
        await session.rollback()


@pytest.mark.asyncio
async def test_channel_override_applies_email_suggest() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        base = await get_or_create_ai_config(session, org_id)
        base.mode = AIMode.AUTO_REPLY
        config = await RuntimeAIConfig.resolve(session, org_id, "EMAIL")
        assert config.mode == AIMode.SUGGEST
        await session.rollback()
