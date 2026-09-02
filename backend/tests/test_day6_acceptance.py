"""Day 6 acceptance scenario."""

from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import Conversation, ConversationStatus, Customer, Organization, Priority, Ticket, User
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.ai.application.ai_service import AIService
from app.modules.ai.application.missed_chat_service import MissedChatService
from app.modules.ai.domain.models import AgentAvailability, AgentStatus
from app.modules.automation.domain.enums import ExecutionStatus
from app.modules.automation.domain.models import Automation, AutomationExecution
from app.modules.conversations.schemas import ConversationCreate
from app.modules.conversations.service import ConversationService
from app.modules.notifications.domain.models import Notification
from app.modules.sla.domain.models import SLATimer


@pytest.mark.asyncio
async def test_day6_billing_message_triggers_automation() -> None:
    from app.modules.automation.application.event_handler import register_automation_handlers

    await register_automation_handlers()
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        user = (await session.execute(select(User).limit(1))).scalar_one()
        customer = Customer(organization_id=org_id, name="Billing Customer")
        session.add(customer)
        await session.flush()

        conv = await ConversationService(session).create_conversation(
            user, ConversationCreate(customer_id=customer.id, channel="WEB_CHAT")
        )

        from app.infrastructure.database.models import Message, SenderType

        msg = Message(
            conversation_id=conv.id,
            sender_type=SenderType.CUSTOMER,
            content="I was charged twice.",
        )
        session.add(msg)
        await session.commit()

        async with AsyncSessionLocal() as ai_session:
            with patch.object(AIService, "run_support_agent") as mock_run:
                from app.modules.ai.domain.models import AIRun, AIRunStatus, AIRunType
                from app.modules.ai.domain.schemas import AIResponse, AgentDecision, IntentLabel

                run = AIRun(
                    conversation_id=conv.id,
                    message_id=msg.id,
                    type=AIRunType.AGENT,
                    status=AIRunStatus.COMPLETED,
                    intent="BILLING",
                    sentiment="NEUTRAL",
                    confidence=0.96,
                )
                mock_run.return_value = (
                    AIResponse(
                        answer="",
                        intent=IntentLabel.BILLING,
                        confidence=0.96,
                        grounded=True,
                        escalation_required=False,
                        decision=AgentDecision.AI_RESOLVE,
                    ),
                    run,
                )
                await AIService(ai_session).process_customer_message(msg.id)
            await ai_session.commit()

        async with AsyncSessionLocal() as verify:
            refreshed = await verify.get(Conversation, conv.id)
            assert refreshed is not None
            assert refreshed.priority == Priority.HIGH
            exec_row = await verify.scalar(
                select(AutomationExecution)
                .join(Automation, Automation.id == AutomationExecution.automation_id)
                .where(AutomationExecution.entity_id == conv.id, Automation.name == "Route Billing")
                .order_by(AutomationExecution.started_at.desc())
            )
            assert exec_row is not None
            assert exec_row.status == ExecutionStatus.COMPLETED
            note = await verify.scalar(select(Notification).where(Notification.user_id == user.id))
            assert note is not None
            timer = await verify.scalar(select(SLATimer).where(SLATimer.conversation_id == conv.id))
            assert timer is not None


@pytest.mark.asyncio
async def test_day6_angry_message_notifies_manager() -> None:
    from app.modules.automation.application.event_handler import register_automation_handlers

    await register_automation_handlers()
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        user = (await session.execute(select(User).limit(1))).scalar_one()
        from app.infrastructure.database.models import Role, RoleName

        manager = await session.scalar(
            select(User)
            .join(Role, User.role_id == Role.id)
            .where(User.organization_id == org_id, Role.name == RoleName.MANAGER)
        )
        if manager is None:
            pytest.skip("Manager not seeded")

        customer = Customer(organization_id=org_id, name="Angry Customer")
        session.add(customer)
        await session.flush()
        conv = await ConversationService(session).create_conversation(
            user, ConversationCreate(customer_id=customer.id, channel="WEB_CHAT")
        )
        from app.infrastructure.database.models import Message, SenderType

        msg = Message(
            conversation_id=conv.id,
            sender_type=SenderType.CUSTOMER,
            content="This is unacceptable!",
        )
        session.add(msg)
        await session.commit()

        async with AsyncSessionLocal() as ai_session:
            with patch.object(AIService, "run_support_agent") as mock_run:
                from app.modules.ai.domain.models import AIRun, AIRunStatus, AIRunType
                from app.modules.ai.domain.schemas import AIResponse, AgentDecision, IntentLabel

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
                        answer="",
                        intent=IntentLabel.TECHNICAL_ISSUE,
                        confidence=0.9,
                        grounded=True,
                        escalation_required=False,
                        decision=AgentDecision.AI_RESOLVE,
                    ),
                    run,
                )
                await AIService(ai_session).process_customer_message(msg.id)
            await ai_session.commit()

        async with AsyncSessionLocal() as verify:
            refreshed = await verify.get(Conversation, conv.id)
            assert refreshed is not None
            assert refreshed.priority == Priority.URGENT
            note = await verify.scalar(select(Notification).where(Notification.user_id == manager.id))
            assert note is not None


@pytest.mark.asyncio
async def test_day6_missed_chat_creates_ticket() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        user = (await session.execute(select(User).limit(1))).scalar_one()

        for row in (await session.execute(select(AgentAvailability))).scalars():
            row.status = AgentStatus.OFFLINE
            row.is_online = False

        customer = Customer(organization_id=org_id, name="Missed")
        session.add(customer)
        await session.flush()
        conv = await ConversationService(session).create_conversation(
            user, ConversationCreate(customer_id=customer.id, channel="WEB_CHAT")
        )
        conv.status = ConversationStatus.WAITING_FOR_AGENT
        await session.flush()

        await MissedChatService(session).check_conversation(conv.id, org_id)
        await session.commit()

        async with AsyncSessionLocal() as verify:
            ticket = await verify.scalar(select(Ticket).where(Ticket.conversation_id == conv.id))
            assert ticket is not None
