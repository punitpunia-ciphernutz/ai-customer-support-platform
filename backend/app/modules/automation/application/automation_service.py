"""Automation CRUD."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.automation.domain.models import Automation, AutomationExecution
from app.modules.automation.domain.schemas import AutomationCreate, AutomationUpdate


class AutomationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_automations(self, organization_id: str) -> list[tuple[Automation, int]]:
        result = await self.db.execute(
            select(Automation).where(Automation.organization_id == organization_id).order_by(Automation.priority.desc())
        )
        automations = list(result.scalars().all())
        counts: dict[str, int] = {}
        if automations:
            exec_result = await self.db.execute(
                select(AutomationExecution.automation_id, func.count())
                .where(AutomationExecution.organization_id == organization_id)
                .group_by(AutomationExecution.automation_id)
            )
            counts = {row[0]: row[1] for row in exec_result.all()}
        return [(a, counts.get(a.id, 0)) for a in automations]

    async def get(self, organization_id: str, automation_id: str) -> Automation | None:
        return await self.db.scalar(
            select(Automation).where(Automation.id == automation_id, Automation.organization_id == organization_id)
        )

    async def create(self, organization_id: str, data: AutomationCreate, created_by: str | None) -> Automation:
        automation = Automation(
            organization_id=organization_id,
            name=data.name,
            description=data.description,
            enabled=data.enabled,
            trigger=data.trigger.model_dump(),
            conditions=data.conditions,
            actions=[a.model_dump() for a in data.actions],
            priority=data.priority,
            created_by=created_by,
        )
        self.db.add(automation)
        await self.db.flush()
        await self.db.refresh(automation)
        return automation

    async def update(self, automation: Automation, data: AutomationUpdate) -> Automation:
        if data.name is not None:
            automation.name = data.name
        if data.description is not None:
            automation.description = data.description
        if data.enabled is not None:
            automation.enabled = data.enabled
        if data.trigger is not None:
            automation.trigger = data.trigger.model_dump()
        if data.conditions is not None:
            automation.conditions = data.conditions
        if data.actions is not None:
            automation.actions = [a.model_dump() for a in data.actions]
        if data.priority is not None:
            automation.priority = data.priority
        await self.db.flush()
        await self.db.refresh(automation)
        return automation

    async def delete(self, automation: Automation) -> None:
        await self.db.delete(automation)
        await self.db.flush()

    async def set_enabled(self, automation: Automation, enabled: bool) -> Automation:
        automation.enabled = enabled
        await self.db.flush()
        return automation
