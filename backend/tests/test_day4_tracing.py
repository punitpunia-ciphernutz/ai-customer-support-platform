"""Day 4 trace and token usage tests."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import Organization
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.ai.application.ai_config_service import get_or_create_ai_config
from app.modules.ai.application.runtime_config import RuntimeAIConfig
from app.modules.ai.domain.schemas import SupportAgentState
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
async def test_support_agent_populates_trace_steps() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        base = await get_or_create_ai_config(session, org_id)
        config = RuntimeAIConfig.from_config(base)
        state = SupportAgentState(
            organization_id=org_id,
            user_message="How do I reset my password?",
        )
        final, latency, tokens = await timed_support_agent(
            state, config=config, llm=EchoLLMProvider(), db_session=session
        )
        assert latency >= 0
        assert tokens["input_tokens"] > 0
        assert tokens["output_tokens"] > 0
        assert len(final.trace_steps) >= 5
        step_names = {s.name for s in final.trace_steps}
        assert "classify_intent" in step_names
        assert "detect_language" in step_names
        assert "calculate_confidence" in step_names
        await session.rollback()
