"""LLM-driven sentiment: normalize validates only; Echo/LLM is source of truth."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from app.modules.ai.application.runtime_config import RuntimeAIConfig
from app.modules.ai.domain.models import AIMode, SentimentLabel
from app.modules.ai.domain.schemas import AIClassification, IntentLabel, MessageKind, SupportAgentState
from app.modules.ai.graphs.classification import run_classification_graph
from app.modules.ai.graphs.support_agent import _normalize_sentiment, timed_support_agent
from app.modules.ai.infrastructure.llm.providers import EchoLLMProvider


def _runtime_config() -> RuntimeAIConfig:
    return RuntimeAIConfig(
        enabled=True,
        mode=AIMode.AUTO_REPLY,
        auto_reply_threshold=0.7,
        escalation_threshold=0.4,
        min_relevance_score=0.35,
        require_knowledge=False,
        escalate_if_unknown=False,
        multilingual_enabled=True,
        hybrid_keyword_weight=0.3,
        missed_chat_timeout_minutes=5,
        ai_response_timeout_seconds=30,
        llm_model="echo",
        allowed_intents=None,
        restricted_intents=None,
        intent_team_map=None,
        organization_id="00000000-0000-0000-0000-000000000001",
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("POSITIVE", "POSITIVE"),
        ("neutral", "NEUTRAL"),
        (SentimentLabel.NEGATIVE, "NEGATIVE"),
        ("ANGRY", "ANGRY"),
        ("angry", "ANGRY"),
        ("frustrated", "NEUTRAL"),  # not a valid label — sanitize only
        ("upset", "NEUTRAL"),
        ("", "NEUTRAL"),
        (None, "NEUTRAL"),
        ("bogus", "NEUTRAL"),
    ],
)
def test_normalize_sentiment_validates_only(raw: str | SentimentLabel | None, expected: str) -> None:
    assert _normalize_sentiment(raw) == expected


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Thanks, that solved it!", SentimentLabel.POSITIVE.value),
        ("How do I reset my password?", SentimentLabel.NEUTRAL.value),
        ("The reset email isn't working", SentimentLabel.NEGATIVE.value),
        ("I'm disappointed with the billing delay", SentimentLabel.NEGATIVE.value),
        ("This is the third time I've contacted you!", SentimentLabel.ANGRY.value),
        # Strong intensity without classic angry/mad keywords from old normalizer list
        ("This is ridiculous — fix your mess now", SentimentLabel.ANGRY.value),
        ("I'm done with this service", SentimentLabel.ANGRY.value),
        ("now i get angry", SentimentLabel.ANGRY.value),
    ],
)
@pytest.mark.asyncio
async def test_echo_llm_sentiment_labels(message: str, expected: str) -> None:
    classification = await EchoLLMProvider().structured_output(message, AIClassification)
    assert classification.sentiment == expected
    assert _normalize_sentiment(classification.sentiment) == expected


class _FixedSentimentLLM(EchoLLMProvider):
    """Returns a forced sentiment while keeping Echo intent heuristics."""

    def __init__(self, sentiment: SentimentLabel) -> None:
        super().__init__()
        self._forced = sentiment

    async def structured_output(self, prompt: str, schema: type[BaseModel], **kwargs: Any) -> BaseModel:
        result = await super().structured_output(prompt, schema, **kwargs)
        if schema is AIClassification and isinstance(result, AIClassification):
            return result.model_copy(update={"sentiment": self._forced})
        return result


@pytest.mark.asyncio
async def test_pipeline_trusts_llm_sentiment_without_keyword_override() -> None:
    """Message has no Echo angry cues; LLM returns ANGRY → pipeline keeps ANGRY."""
    message = "I have been waiting an hour and still have no answer"
    llm = _FixedSentimentLLM(SentimentLabel.ANGRY)
    # Echo alone would not mark this ANGRY
    echo_only = await EchoLLMProvider().structured_output(message, AIClassification)
    assert echo_only.sentiment != SentimentLabel.ANGRY.value

    classification = await run_classification_graph(message, llm=llm)
    assert classification.sentiment == SentimentLabel.ANGRY
    assert _normalize_sentiment(classification.sentiment) == SentimentLabel.ANGRY.value

    state = SupportAgentState(user_message=message)
    final, _, _ = await timed_support_agent(state, config=_runtime_config(), llm=llm)
    assert final.sentiment == SentimentLabel.ANGRY.value


@pytest.mark.asyncio
async def test_pipeline_does_not_upgrade_negative_via_message_keywords() -> None:
    """Even if message looks angry, normalizer must not override LLM NEGATIVE."""
    message = "This is terrible and unacceptable!!!"
    llm = _FixedSentimentLLM(SentimentLabel.NEGATIVE)
    classification = await run_classification_graph(message, llm=llm)
    assert _normalize_sentiment(classification.sentiment) == SentimentLabel.NEGATIVE.value

    state = SupportAgentState(user_message=message)
    final, _, _ = await timed_support_agent(state, config=_runtime_config(), llm=llm)
    assert final.sentiment == SentimentLabel.NEGATIVE.value


@pytest.mark.asyncio
async def test_classification_schema_rejects_invalid_sentiment_at_parse() -> None:
    with pytest.raises(Exception):
        AIClassification(
            intent=IntentLabel.OTHER,
            sentiment="frustrated",  # type: ignore[arg-type]
            confidence=0.5,
            message_kind=MessageKind.SUPPORT_REQUEST,
        )
