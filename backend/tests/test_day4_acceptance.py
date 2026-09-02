"""Day 4 acceptance and unit tests (offline Echo LLM)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import AIControlMode, Organization
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.ai.application.evaluation_service import EVALUATION_CASES, EvaluationService
from app.modules.ai.application.grounding_validator import GroundingValidator
from app.modules.ai.domain.schemas import AgentDecision, RetrievedDocument
from app.modules.ai.infrastructure.llm.providers import EchoLLMProvider
from app.modules.conversations.service import ConversationService


@pytest.mark.asyncio
async def test_grounding_fails_without_sources() -> None:
    result = await GroundingValidator(EchoLLMProvider()).validate(
        "You can reset your password anytime.", []
    )
    assert not result.grounded


@pytest.mark.asyncio
async def test_takeover_blocks_ai_control_mode() -> None:
    async with AsyncSessionLocal() as session:
        from app.infrastructure.database.models import Conversation, Customer, User
        from app.modules.conversations.schemas import ConversationCreate

        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        user = (await session.execute(select(User).limit(1))).scalar_one()
        customer = Customer(organization_id=org_id, name="Takeover Test")
        session.add(customer)
        await session.flush()
        conv = await ConversationService(session).create_conversation(
            user, ConversationCreate(customer_id=customer.id, channel="WEB_CHAT")
        )
        updated = await ConversationService(session).takeover(user, conv.id)
        assert updated.ai_control_mode == AIControlMode.HUMAN_CONTROL
        restored = await ConversationService(session).return_to_ai(user, conv.id)
        assert restored.ai_control_mode == AIControlMode.AI_CONTROL
        await session.rollback()


def test_evaluation_case_count() -> None:
    assert len(EVALUATION_CASES) >= 20


@pytest.mark.asyncio
async def test_evaluation_suite_runs_offline() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        report = await EvaluationService(session).run_suite(org_id)
        assert report.total_cases >= 20
        assert report.intent_accuracy >= 0
        await session.rollback()
