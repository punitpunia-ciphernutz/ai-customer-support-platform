"""Agent availability and business hours."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.application.ai_config_service import get_or_create_ai_config
from app.modules.ai.domain.models import AgentAvailability


class AvailabilityService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def is_agent_available(self, organization_id: str) -> bool:
        count = await self.db.scalar(
            select(func.count())
            .select_from(AgentAvailability)
            .where(
                AgentAvailability.organization_id == organization_id,
                AgentAvailability.is_online.is_(True),
            )
        )
        return bool(count and count > 0)

    async def is_within_business_hours(self, organization_id: str) -> bool:
        config = await get_or_create_ai_config(self.db, organization_id)
        hours = config.business_hours or {}
        schedule = hours.get("schedule") or {}
        if not schedule:
            return True
        now = datetime.now(timezone.utc)
        day = now.strftime("%A").lower()
        day_schedule = schedule.get(day)
        if not day_schedule:
            return False
        start = day_schedule.get("start", "09:00")
        end = day_schedule.get("end", "18:00")
        current = now.strftime("%H:%M")
        return start <= current <= end

    async def get_availability(self, organization_id: str) -> list[AgentAvailability]:
        result = await self.db.execute(
            select(AgentAvailability).where(AgentAvailability.organization_id == organization_id)
        )
        return list(result.scalars().all())

    async def set_online(self, user_id: str, organization_id: str, is_online: bool) -> AgentAvailability:
        row = await self.db.scalar(select(AgentAvailability).where(AgentAvailability.user_id == user_id))
        if row is None:
            row = AgentAvailability(user_id=user_id, organization_id=organization_id, is_online=is_online)
            self.db.add(row)
        else:
            row.is_online = is_online
        await self.db.flush()
        await self.db.refresh(row)
        return row
