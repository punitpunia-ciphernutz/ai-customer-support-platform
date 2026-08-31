"""AI run persistence, configuration, and structured schemas."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class AIRunType(StrEnum):
    CLASSIFICATION = "CLASSIFICATION"
    GENERATION = "GENERATION"
    SUMMARY = "SUMMARY"
    RETRIEVAL = "RETRIEVAL"
    AGENT = "AGENT"


class AIRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"  # legacy Day 2 classify runs
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AIMode(StrEnum):
    DRAFT_ONLY = "DRAFT_ONLY"
    SUGGEST = "SUGGEST"
    AUTO_REPLY = "AUTO_REPLY"


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
    intent: Mapped[str | None] = mapped_column(String(64))
    retrieval_count: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float | None] = mapped_column(Float)
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
    allowed_intents: Mapped[list[str] | None] = mapped_column(JSONB)
    restricted_intents: Mapped[list[str] | None] = mapped_column(JSONB, default=list)
    intent_team_map: Mapped[dict[str, str] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
