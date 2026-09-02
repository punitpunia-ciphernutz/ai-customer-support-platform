"""Verify automations run when events are published from Celery worker context."""

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import Customer, Message, Organization, SenderType, User
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.ai.application.ai_service import AIService
from app.modules.ai.domain.models import AIRun, AIRunStatus, AIRunType
from app.modules.ai.domain.schemas import AIResponse, AgentDecision, IntentLabel
from app.modules.ai.infrastructure.llm.providers import EchoLLMProvider
from app.modules.automation.domain.enums import ExecutionStatus
from app.modules.automation.domain.models import Automation, AutomationExecution
from app.modules.conversations.schemas import ConversationCreate
from app.modules.conversations.service import ConversationService
from unittest.mock import patch


def test_celery_app_registers_automation_handlers() -> None:
    from app.infrastructure.events import event_bus
    from app.workers import celery_app  # noqa: F401

    assert celery_app is not None
    assert event_bus._handlers  # noqa: SLF001


@pytest.mark.asyncio
async def test_message_received_automation_runs_without_fastapi_lifespan() -> None:
    """Celery processes AI in a separate process — handlers must not depend on FastAPI startup."""
    from app.modules.automation.application.event_handler import register_automation_handlers

    register_automation_handlers()

    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        user = (await session.execute(select(User).limit(1))).scalar_one()
        customer = Customer(organization_id=org_id, name="Angry Celery Path")
        session.add(customer)
        await session.flush()

        session.add(
            Automation(
                organization_id=org_id,
                name="Test for angry celery",
                enabled=True,
                trigger={"type": "MESSAGE_RECEIVED"},
                conditions={
                    "logic": "AND",
                    "conditions": [{"field": "sentiment", "operator": "EQUALS", "value": "ANGRY"}],
                },
                actions=[{"type": "CREATE_TICKET", "config": {"title": "Angry automation ticket"}}],
                priority=100,
            )
        )
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
        await session.commit()

    async with AsyncSessionLocal() as ai_session:
        with patch.object(AIService, "run_support_agent") as mock_run:
            run = AIRun(
                conversation_id=conv.id,
                message_id=msg.id,
                type=AIRunType.AGENT,
                status=AIRunStatus.COMPLETED,
                intent="TECHNICAL_ISSUE",
                sentiment="ANGRY",
                confidence=0.9,
            )
            mock_run.return_value = (
                AIResponse(
                    answer="Connecting you with support.",
                    intent=IntentLabel.TECHNICAL_ISSUE,
                    confidence=0.9,
                    grounded=True,
                    escalation_required=True,
                    decision=AgentDecision.ESCALATE,
                ),
                run,
            )
            await AIService(ai_session, llm=EchoLLMProvider()).process_customer_message(msg.id)
        await ai_session.commit()

    async with AsyncSessionLocal() as verify:
        execution = await verify.scalar(
            select(AutomationExecution)
            .join(Automation, Automation.id == AutomationExecution.automation_id)
            .where(
                AutomationExecution.entity_id == conv.id,
                Automation.name == "Test for angry celery",
            )
        )
        assert execution is not None
        assert execution.status in {ExecutionStatus.COMPLETED, ExecutionStatus.SKIPPED}
