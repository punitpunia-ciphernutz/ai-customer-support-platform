"""AI run persistence, configuration, prompts, evaluation, and structured schemas."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.models import AIControlMode, TicketSource


class AIRunType(StrEnum):
    CLASSIFICATION = "CLASSIFICATION"
    GENERATION = "GENERATION"
    SUMMARY = "SUMMARY"
    RETRIEVAL = "RETRIEVAL"
    AGENT = "AGENT"
    EVALUATION = "EVALUATION"


class AIRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"  # legacy Day 2 classify runs
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AIMode(StrEnum):
    DRAFT_ONLY = "DRAFT_ONLY"  # Day 4: KNOWLEDGE_BASE
    SUGGEST = "SUGGEST"  # Day 4: SUGGEST_REPLY
    AUTO_REPLY = "AUTO_REPLY"  # Day 4: AUTOPILOT


class AgentDecisionType(StrEnum):
    AI_RESOLVE = "AI_RESOLVE"
    ESCALATE = "ESCALATE"
    SUGGEST_ONLY = "SUGGEST_ONLY"


class SentimentLabel(StrEnum):
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"
    ANGRY = "ANGRY"


class AgentStatus(StrEnum):
    ONLINE = "ONLINE"
    AWAY = "AWAY"
    OFFLINE = "OFFLINE"


class EvaluationBehavior(StrEnum):
    ANSWER = "ANSWER"
    ESCALATE = "ESCALATE"
    SUGGEST = "SUGGEST"


# Day 4 display labels for API/UI
AI_MODE_DISPLAY: dict[AIMode, str] = {
    AIMode.DRAFT_ONLY: "KNOWLEDGE_BASE",
    AIMode.SUGGEST: "SUGGEST_REPLY",
    AIMode.AUTO_REPLY: "AUTOPILOT",
}


class AIRun(Base):
    __tablename__ = "ai_runs"
    __table_args__ = (
        UniqueConstraint("processing_key", name="uq_ai_runs_processing_key"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id"), index=True)
    message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id"), index=True)
    type: Mapped[AIRunType] = mapped_column(Enum(AIRunType, name="ai_run_type"), nullable=False)
    status: Mapped[AIRunStatus] = mapped_column(
        Enum(AIRunStatus, name="ai_run_status"), default=AIRunStatus.PENDING, nullable=False
    )
    model: Mapped[str | None] = mapped_column(String(128))
    graph_version: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(128))
    intent: Mapped[str | None] = mapped_column(String(64))
    retrieval_count: Mapped[int | None] = mapped_column(Integer)
    retrieval_score: Mapped[float | None] = mapped_column(Float)
    grounding_score: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    confidence_components: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    decision: Mapped[str | None] = mapped_column(String(32))
    language: Mapped[str | None] = mapped_column(String(16))
    sentiment: Mapped[str | None] = mapped_column(String(32))
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float)
    trace: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    processing_key: Mapped[str | None] = mapped_column(String(128), index=True)
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AIConfig(Base):
    __tablename__ = "ai_configs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, unique=True, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    mode: Mapped[AIMode] = mapped_column(
        Enum(AIMode, name="ai_mode"), default=AIMode.AUTO_REPLY, nullable=False
    )
    auto_reply_threshold: Mapped[float] = mapped_column(Float, default=0.85, nullable=False)
    escalation_threshold: Mapped[float] = mapped_column(Float, default=0.85, nullable=False)
    min_relevance_score: Mapped[float] = mapped_column(Float, default=0.35, nullable=False)
    require_knowledge: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    escalate_if_unknown: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    multilingual_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    hybrid_keyword_weight: Mapped[float] = mapped_column(Float, default=0.3, nullable=False)
    business_hours: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    missed_chat_timeout_minutes: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    ai_response_timeout_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    allowed_intents: Mapped[list[str] | None] = mapped_column(JSONB)
    restricted_intents: Mapped[list[str] | None] = mapped_column(JSONB, default=list)
    intent_team_map: Mapped[dict[str, str] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Prompt(Base):
    __tablename__ = "prompts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("prompt_id", "version", name="uq_prompt_version"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    prompt_id: Mapped[str] = mapped_column(ForeignKey("prompts.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(String(128))
    configuration: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BotConfiguration(Base):
    """Per-channel bot mode and threshold overrides."""

    __tablename__ = "bot_configurations"
    __table_args__ = (
        UniqueConstraint("organization_id", "channel", name="uq_bot_config_org_channel"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    mode: Mapped[AIMode | None] = mapped_column(Enum(AIMode, name="ai_mode", create_constraint=False))
    auto_reply_threshold: Mapped[float | None] = mapped_column(Float)
    escalation_threshold: Mapped[float | None] = mapped_column(Float)
    min_relevance_score: Mapped[float | None] = mapped_column(Float)
    require_knowledge: Mapped[bool | None] = mapped_column(Boolean)
    multilingual_enabled: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AIEvaluation(Base):
    __tablename__ = "ai_evaluations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    case_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cases: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AIEvaluationResult(Base):
    __tablename__ = "ai_evaluation_results"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("ai_evaluations.id"), nullable=False, index=True)
    ai_run_id: Mapped[str | None] = mapped_column(ForeignKey("ai_runs.id"), index=True)
    case_index: Mapped[int] = mapped_column(Integer, nullable=False)
    input_message: Mapped[str] = mapped_column(Text, nullable=False)
    expected: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    actual: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scores: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentAvailability(Base):
    __tablename__ = "agent_availability"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_agent_availability_user"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    is_online: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[AgentStatus] = mapped_column(
        Enum(AgentStatus, name="agent_status"), default=AgentStatus.OFFLINE, nullable=False
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_conversation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    schedule: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
