"""Automation domain schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.modules.automation.domain.enums import (
    ActionType,
    AutomationTriggerType,
    ConditionOperator,
    ExecutionStatus,
    StepType,
)


class TriggerConfig(BaseModel):
    type: AutomationTriggerType


class ConditionLeaf(BaseModel):
    field: str
    operator: ConditionOperator
    value: Any = None


class ConditionGroup(BaseModel):
    logic: str = "AND"
    conditions: list[Any] = Field(default_factory=list)


class ActionConfig(BaseModel):
    type: ActionType
    value: Any = None
    config: dict[str, Any] = Field(default_factory=dict)


class AutomationCreate(BaseModel):
    name: str
    description: str | None = None
    enabled: bool = True
    trigger: TriggerConfig
    conditions: dict[str, Any] | None = None
    actions: list[ActionConfig]
    priority: int = 0


class AutomationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    trigger: TriggerConfig | None = None
    conditions: dict[str, Any] | None = None
    actions: list[ActionConfig] | None = None
    priority: int | None = None


class AutomationOut(BaseModel):
    id: str
    organization_id: str
    name: str
    description: str | None
    enabled: bool
    trigger: dict[str, Any]
    conditions: dict[str, Any] | None
    actions: list[dict[str, Any]]
    priority: int
    created_by: str | None
    created_at: datetime
    updated_at: datetime
    execution_count: int = 0

    model_config = {"from_attributes": True}


class ExecutionStepOut(BaseModel):
    id: str
    step_type: StepType
    configuration: dict[str, Any]
    status: ExecutionStatus
    result: dict[str, Any] | None
    error: str | None
    duration_ms: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ExecutionOut(BaseModel):
    id: str
    automation_id: str
    organization_id: str
    trigger_event: str
    entity_type: str
    entity_id: str
    status: ExecutionStatus
    started_at: datetime
    completed_at: datetime | None
    error: str | None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    steps: list[ExecutionStepOut] = Field(default_factory=list)

    model_config = {"from_attributes": True, "populate_by_name": True}
