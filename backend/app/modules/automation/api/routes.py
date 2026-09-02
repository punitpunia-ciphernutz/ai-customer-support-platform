from datetime import date, time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_db
from app.modules.automation.application.automation_service import AutomationService
from app.modules.automation.domain.models import AutomationExecution, AutomationExecutionStep
from app.modules.automation.domain.schemas import (
    AutomationCreate,
    AutomationOut,
    AutomationUpdate,
    ExecutionOut,
    ExecutionStepOut,
)
from app.modules.auth.permissions import AI_READ, AI_WRITE

router = APIRouter(prefix="/automations", tags=["automations"])


def _automation_out(automation: Any, execution_count: int = 0) -> AutomationOut:
    return AutomationOut(
        id=automation.id,
        organization_id=automation.organization_id,
        name=automation.name,
        description=automation.description,
        enabled=automation.enabled,
        trigger=automation.trigger,
        conditions=automation.conditions,
        actions=automation.actions,
        priority=automation.priority,
        created_by=automation.created_by,
        created_at=automation.created_at,
        updated_at=automation.updated_at,
        execution_count=execution_count,
    )


@router.get("", response_model=list[AutomationOut])
async def list_automations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_READ)),
):
    rows = await AutomationService(db).list_automations(user.organization_id)
    return [_automation_out(a, count) for a, count in rows]


@router.post("", response_model=AutomationOut, status_code=status.HTTP_201_CREATED)
async def create_automation(
    body: AutomationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_WRITE)),
):
    automation = await AutomationService(db).create(user.organization_id, body, user.id)
    await db.commit()
    return _automation_out(automation)


@router.get("/{automation_id}", response_model=AutomationOut)
async def get_automation(
    automation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_READ)),
):
    automation = await AutomationService(db).get(user.organization_id, automation_id)
    if automation is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    return _automation_out(automation)


@router.patch("/{automation_id}", response_model=AutomationOut)
async def update_automation(
    automation_id: str,
    body: AutomationUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_WRITE)),
):
    automation = await AutomationService(db).get(user.organization_id, automation_id)
    if automation is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    automation = await AutomationService(db).update(automation, body)
    await db.commit()
    return _automation_out(automation)


@router.delete("/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_automation(
    automation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_WRITE)),
):
    automation = await AutomationService(db).get(user.organization_id, automation_id)
    if automation is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    await AutomationService(db).delete(automation)
    await db.commit()


@router.post("/{automation_id}/enable", response_model=AutomationOut)
async def enable_automation(
    automation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_WRITE)),
):
    automation = await AutomationService(db).get(user.organization_id, automation_id)
    if automation is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    automation = await AutomationService(db).set_enabled(automation, True)
    await db.commit()
    return _automation_out(automation)


@router.post("/{automation_id}/disable", response_model=AutomationOut)
async def disable_automation(
    automation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_WRITE)),
):
    automation = await AutomationService(db).get(user.organization_id, automation_id)
    if automation is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    automation = await AutomationService(db).set_enabled(automation, False)
    await db.commit()
    return _automation_out(automation)


@router.get("/{automation_id}/executions", response_model=list[ExecutionOut])
async def list_executions(
    automation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_READ)),
):
    automation = await AutomationService(db).get(user.organization_id, automation_id)
    if automation is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    result = await db.execute(
        select(AutomationExecution)
        .where(AutomationExecution.automation_id == automation_id)
        .order_by(AutomationExecution.started_at.desc())
        .limit(50)
    )
    executions = list(result.scalars().all())
    return [
        ExecutionOut(
            id=e.id,
            automation_id=e.automation_id,
            organization_id=e.organization_id,
            trigger_event=e.trigger_event,
            entity_type=e.entity_type,
            entity_id=e.entity_id,
            status=e.status,
            started_at=e.started_at,
            completed_at=e.completed_at,
            error=e.error,
            metadata=e.metadata_ or {},
        )
        for e in executions
    ]


executions_router = APIRouter(prefix="/automation-executions", tags=["automations"])


@executions_router.get("/{execution_id}", response_model=ExecutionOut)
async def get_execution(
    execution_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_READ)),
):
    execution = await db.scalar(
        select(AutomationExecution).where(
            AutomationExecution.id == execution_id,
            AutomationExecution.organization_id == user.organization_id,
        )
    )
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    steps_result = await db.execute(
        select(AutomationExecutionStep)
        .where(AutomationExecutionStep.execution_id == execution_id)
        .order_by(AutomationExecutionStep.created_at.asc())
    )
    steps = [
        ExecutionStepOut(
            id=s.id,
            step_type=s.step_type,
            configuration=s.configuration,
            status=s.status,
            result=s.result,
            error=s.error,
            duration_ms=s.duration_ms,
            created_at=s.created_at,
        )
        for s in steps_result.scalars().all()
    ]
    return ExecutionOut(
        id=execution.id,
        automation_id=execution.automation_id,
        organization_id=execution.organization_id,
        trigger_event=execution.trigger_event,
        entity_type=execution.entity_type,
        entity_id=execution.entity_id,
        status=execution.status,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        error=execution.error,
        metadata=execution.metadata_ or {},
        steps=steps,
    )
