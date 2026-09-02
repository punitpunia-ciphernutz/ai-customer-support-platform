"""Automation execution orchestration."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.audit import write_audit
from app.infrastructure.database.models import ActorType
from app.modules.automation.application.action_service import execute_action
from app.modules.automation.application.condition_service import evaluate_conditions
from app.modules.automation.application.context_builder import ContextBuilder
from app.modules.automation.application.execution_context import automation_execution_depth
from app.modules.automation.domain.enums import EVENT_TO_TRIGGER, ExecutionStatus, StepType
from app.modules.automation.domain.models import Automation, AutomationExecution, AutomationExecutionStep

MAX_EXECUTION_DEPTH = 3


class ExecutionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def execute_for_event(
        self,
        *,
        organization_id: str,
        event_name: str,
        payload: dict[str, Any],
        execution_depth: int = 0,
        trigger_event_id: str | None = None,
    ) -> list[AutomationExecution]:
        if execution_depth >= MAX_EXECUTION_DEPTH:
            return []

        trigger_type = EVENT_TO_TRIGGER.get(event_name)
        if trigger_type is None:
            return []

        depth_token = automation_execution_depth.set(execution_depth)
        try:
            automations = await self._matching_automations(organization_id, trigger_type.value)
            ctx = await ContextBuilder(self.db).build(
                organization_id,
                payload,
                execution_depth=execution_depth,
                trigger_event_id=trigger_event_id,
            )
            results: list[AutomationExecution] = []
            for automation in automations:
                execution = await self._run_automation(
                    automation,
                    event_name,
                    ctx,
                    payload,
                    execution_depth,
                    trigger_event_id,
                )
                if execution:
                    results.append(execution)
            return results
        finally:
            automation_execution_depth.reset(depth_token)

    async def _matching_automations(self, organization_id: str, trigger_type: str) -> list[Automation]:
        result = await self.db.execute(
            select(Automation)
            .where(Automation.organization_id == organization_id, Automation.enabled.is_(True))
            .order_by(Automation.priority.desc(), Automation.created_at.asc())
        )
        automations = list(result.scalars().all())
        return [a for a in automations if (a.trigger or {}).get("type") == trigger_type]

    async def _run_automation(
        self,
        automation: Automation,
        event_name: str,
        ctx: Any,
        payload: dict[str, Any],
        execution_depth: int,
        trigger_event_id: str | None,
    ) -> AutomationExecution | None:
        entity_type = "conversation" if ctx.conversation_id else "ticket" if ctx.ticket_id else "organization"
        entity_id = ctx.conversation_id or ctx.ticket_id or ctx.organization_id

        execution = AutomationExecution(
            automation_id=automation.id,
            organization_id=automation.organization_id,
            trigger_event=event_name,
            entity_type=entity_type,
            entity_id=entity_id,
            status=ExecutionStatus.RUNNING,
            metadata_={
                "execution_depth": execution_depth,
                "trigger_event_id": trigger_event_id,
                "payload": payload,
            },
        )
        self.db.add(execution)
        await self.db.flush()

        cond_step = AutomationExecutionStep(
            execution_id=execution.id,
            step_type=StepType.CONDITION,
            configuration=automation.conditions or {},
            status=ExecutionStatus.RUNNING,
        )
        self.db.add(cond_step)
        await self.db.flush()

        start = time.monotonic()
        try:
            matched = evaluate_conditions(ctx, automation.conditions)
            cond_step.duration_ms = int((time.monotonic() - start) * 1000)
            cond_step.status = ExecutionStatus.COMPLETED if matched else ExecutionStatus.SKIPPED
            cond_step.result = {"matched": matched}
            if not matched:
                execution.status = ExecutionStatus.SKIPPED
                from datetime import datetime, timezone

                execution.completed_at = datetime.now(timezone.utc)
                await self.db.flush()
                return execution

            for action in automation.actions or []:
                action_step = AutomationExecutionStep(
                    execution_id=execution.id,
                    step_type=StepType.ACTION,
                    configuration=action,
                    status=ExecutionStatus.RUNNING,
                )
                self.db.add(action_step)
                await self.db.flush()
                action_start = time.monotonic()
                try:
                    result = await execute_action(self.db, ctx, action)
                    action_step.result = result
                    action_step.status = ExecutionStatus.COMPLETED
                except Exception as exc:  # noqa: BLE001
                    action_step.status = ExecutionStatus.FAILED
                    action_step.error = str(exc)[:2000]
                    execution.status = ExecutionStatus.FAILED
                    execution.error = str(exc)[:2000]
                    break
                finally:
                    action_step.duration_ms = int((time.monotonic() - action_start) * 1000)
                    await self.db.flush()

            if execution.status == ExecutionStatus.RUNNING:
                execution.status = ExecutionStatus.COMPLETED
        except Exception as exc:  # noqa: BLE001
            execution.status = ExecutionStatus.FAILED
            execution.error = str(exc)[:2000]
            cond_step.status = ExecutionStatus.FAILED
            cond_step.error = str(exc)[:2000]
        finally:
            from datetime import datetime, timezone

            execution.completed_at = datetime.now(timezone.utc)
            await self.db.flush()
            if execution.status in {ExecutionStatus.COMPLETED, ExecutionStatus.FAILED}:
                await write_audit(
                    self.db,
                    organization_id=automation.organization_id,
                    actor_type=ActorType.SYSTEM,
                    actor_id=None,
                    action=f"automation.{execution.status.value.lower()}",
                    entity_type="automation_execution",
                    entity_id=execution.id,
                    new_value={
                        "automation_id": automation.id,
                        "automation_name": automation.name,
                        "trigger_event": event_name,
                        "status": execution.status.value,
                        "error": execution.error,
                    },
                )

        return execution
