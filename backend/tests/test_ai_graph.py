"""AI graph and classification tests."""

import pytest

from app.modules.ai.domain.schemas import IntentLabel
from app.modules.ai.graphs.classification import run_classification_graph
from app.modules.ai.graphs.minimal import run_minimal_graph
from app.modules.ai.infrastructure.llm.providers import EchoLLMProvider


@pytest.mark.asyncio
async def test_minimal_graph_echo() -> None:
    result = await run_minimal_graph("ping")
    assert "ping" in result["output"]


@pytest.mark.asyncio
async def test_classification_account_access() -> None:
    result = await run_classification_graph(
        "I cannot log into my account",
        llm=EchoLLMProvider(),
    )
    assert result.intent == IntentLabel.ACCOUNT_ACCESS
    assert result.language == "en"
    assert 0.0 <= result.confidence <= 1.0
