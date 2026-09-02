"""Automation persistence models."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.modules.automation.domain.enums import ExecutionStatus, StepType


class Automation(Base):
    __tablename__ = "automations"
    __table_args__ = (
        Index("ix_automations_org_enabled_priority", "organization_id", "enabled", "priority"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    trigger: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    conditions: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    actions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AutomationExecution(Base):
    __tablename__ = "automation_executions"
    __table_args__ = (
        Index("ix_automation_executions_entity", "entity_type", "entity_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    automation_id: Mapped[str] = mapped_column(ForeignKey("automations.id"), nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    trigger_event: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(ExecutionStatus, name="automation_execution_status"), default=ExecutionStatus.RUNNING, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)


class AutomationExecutionStep(Base):
    __tablename__ = "automation_execution_steps"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    execution_id: Mapped[str] = mapped_column(
        ForeignKey("automation_executions.id"), nullable=False, index=True
    )
    step_type: Mapped[StepType] = mapped_column(Enum(StepType, name="automation_step_type"), nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(ExecutionStatus, name="automation_execution_status", create_constraint=False),
        default=ExecutionStatus.RUNNING,
        nullable=False,
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
