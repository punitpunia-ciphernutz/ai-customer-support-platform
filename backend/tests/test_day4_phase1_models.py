"""Day 4 Phase 1 — database models and migration smoke tests."""

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.infrastructure.database.models import AIControlMode, Conversation, TicketSource
from app.modules.ai.domain.models import (
    AIConfig,
    AIEvaluation,
    BotConfiguration,
    Prompt,
    PromptVersion,
)
from app.modules.ai.domain.schemas import AgentDecision
from app.modules.ai.domain.schemas import (
    AIHandoffPackage,
    AIRunTraceStep,
    ConfidenceBreakdown,
    ConfidenceComponents,
    EvaluationCase,
    GroundingResult,
)
from app.modules.ai.domain.models import AI_MODE_DISPLAY, AIMode, EvaluationBehavior


def test_day4_schemas_instantiate() -> None:
    breakdown = ConfidenceBreakdown(
        final=0.72,
        components=ConfidenceComponents(
            intent=0.94, retrieval=0.61, grounding=0.78, context=0.85, policy=1.0
        ),
        decision=AgentDecision.ESCALATE,
        reasons=["Knowledge relevance below threshold"],
    )
    assert breakdown.final == 0.72

    grounding = GroundingResult(grounded=False, score=0.2, unsupported_claims=["fake policy"])
    assert not grounding.grounded

    handoff = AIHandoffPackage(
        customer_name="John Doe",
        issue_summary="API errors",
        intent="TECHNICAL_ISSUE",
        ai_confidence=0.61,
        what_ai_tried="Explained rate limits",
        why_escalated="Insufficient knowledge",
        recommended_action="Technical investigation",
    )
    assert handoff.customer_name == "John Doe"

    step = AIRunTraceStep(name="retrieve_knowledge", status="completed", duration_ms=120)
    assert step.duration_ms == 120

    case = EvaluationCase(
        input="How do I reset my password?",
        expected_behavior=EvaluationBehavior.ANSWER,
        category="FAQ",
    )
    assert case.expected_behavior == EvaluationBehavior.ANSWER


def test_ai_mode_display_mapping() -> None:
    assert AI_MODE_DISPLAY[AIMode.DRAFT_ONLY] == "KNOWLEDGE_BASE"
    assert AI_MODE_DISPLAY[AIMode.SUGGEST] == "SUGGEST_REPLY"
    assert AI_MODE_DISPLAY[AIMode.AUTO_REPLY] == "AUTOPILOT"


def test_day4_migration_tables_exist() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    for table in (
        "prompts",
        "prompt_versions",
        "bot_configurations",
        "ai_evaluations",
        "ai_evaluation_results",
        "agent_availability",
    ):
        assert table in tables, f"Missing table {table}"

    conv_cols = {c["name"] for c in inspector.get_columns("conversations")}
    assert "ai_control_mode" in conv_cols
    assert "conversation_summary" in conv_cols

    ticket_cols = {c["name"] for c in inspector.get_columns("tickets")}
    assert "source" in ticket_cols
    assert "customer_id" in ticket_cols

    run_cols = {c["name"] for c in inspector.get_columns("ai_runs")}
    assert "grounding_score" in run_cols
    assert "trace" in run_cols
    assert "prompt_version" in run_cols


def test_seed_prompts_and_evaluation() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    with Session(engine) as session:
        prompt = session.scalar(select(Prompt).where(Prompt.name == "support_agent_system"))
        assert prompt is not None
        version = session.scalar(
            select(PromptVersion).where(PromptVersion.prompt_id == prompt.id, PromptVersion.active.is_(True))
        )
        assert version is not None
        assert "support agent" in version.template.lower()

        evaluation = session.scalar(select(AIEvaluation).where(AIEvaluation.name == "Day 4 Baseline"))
        assert evaluation is not None
        assert evaluation.case_count >= 1

        config = session.scalar(select(AIConfig))
        assert config is not None
        assert config.min_relevance_score == 0.35
        assert config.business_hours is not None

        bot = session.scalar(select(BotConfiguration).where(BotConfiguration.channel == "WEB_CHAT"))
        assert bot is not None


def test_enum_values() -> None:
    assert AIControlMode.AI_CONTROL.value == "AI_CONTROL"
    assert TicketSource.AI_ESCALATION.value == "AI_ESCALATION"
