"""SLA timer foundation."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import Priority
from app.modules.business_hours.application.service import BusinessHoursService
from app.modules.sla.domain.models import SLAPolicy, SLATimer, SLATimerStatus, SLATimerType


class SLAService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.business_hours = BusinessHoursService(db)

    async def start_timers_for_conversation(
        self,
        organization_id: str,
        conversation_id: str,
        priority: Priority | str,
    ) -> list[SLATimer]:
        priority_str = priority.value if hasattr(priority, "value") else str(priority)
        policies = await self._matching_policies(organization_id, priority_str)
        hours = await self.business_hours.get_default(organization_id)
        now = datetime.now(timezone.utc)
        timers: list[SLATimer] = []
        for policy in policies:
            for timer_type, minutes in (
                (SLATimerType.FIRST_RESPONSE, policy.first_response_minutes),
                (SLATimerType.RESOLUTION, policy.resolution_minutes),
            ):
                existing = await self.db.scalar(
                    select(SLATimer).where(
                        SLATimer.conversation_id == conversation_id,
                        SLATimer.type == timer_type,
                        SLATimer.status.in_([SLATimerStatus.RUNNING, SLATimerStatus.PAUSED]),
                    )
                )
                if existing:
                    continue
                due_at = now
                if hours:
                    due_at = self.business_hours.add_business_minutes(organization_id, hours, now, minutes)
                else:
                    from datetime import timedelta

                    due_at = now + timedelta(minutes=minutes)
                timer = SLATimer(
                    organization_id=organization_id,
                    sla_policy_id=policy.id,
                    conversation_id=conversation_id,
                    type=timer_type,
                    started_at=now,
                    due_at=due_at,
                    status=SLATimerStatus.RUNNING,
                )
                self.db.add(timer)
                timers.append(timer)
        await self.db.flush()
        return timers

    async def complete_first_response(self, conversation_id: str) -> None:
        await self._complete_type(conversation_id, SLATimerType.FIRST_RESPONSE)

    async def complete_resolution(self, conversation_id: str) -> None:
        await self._complete_type(conversation_id, SLATimerType.RESOLUTION)

    async def pause_timers(self, conversation_id: str) -> None:
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(SLATimer).where(
                SLATimer.conversation_id == conversation_id,
                SLATimer.status == SLATimerStatus.RUNNING,
            )
        )
        for timer in result.scalars().all():
            timer.status = SLATimerStatus.PAUSED
            timer.paused_at = now
        await self.db.flush()

    async def resume_timers(self, conversation_id: str) -> None:
        result = await self.db.execute(
            select(SLATimer).where(
                SLATimer.conversation_id == conversation_id,
                SLATimer.status == SLATimerStatus.PAUSED,
            )
        )
        for timer in result.scalars().all():
            timer.status = SLATimerStatus.RUNNING
            timer.paused_at = None
        await self.db.flush()

    async def check_breaches(self, organization_id: str) -> int:
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(SLATimer).where(
                SLATimer.organization_id == organization_id,
                SLATimer.status == SLATimerStatus.RUNNING,
                SLATimer.due_at < now,
            )
        )
        count = 0
        for timer in result.scalars().all():
            timer.status = SLATimerStatus.BREACHED
            timer.breached_at = now
            count += 1
        await self.db.flush()
        return count

    async def _complete_type(self, conversation_id: str, timer_type: SLATimerType) -> None:
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(SLATimer).where(
                SLATimer.conversation_id == conversation_id,
                SLATimer.type == timer_type,
                SLATimer.status.in_([SLATimerStatus.RUNNING, SLATimerStatus.PAUSED]),
            )
        )
        for timer in result.scalars().all():
            timer.status = SLATimerStatus.COMPLETED
            timer.completed_at = now
        await self.db.flush()

    async def _matching_policies(self, organization_id: str, priority: str) -> list[SLAPolicy]:
        result = await self.db.execute(
            select(SLAPolicy).where(SLAPolicy.organization_id == organization_id, SLAPolicy.enabled.is_(True))
        )
        policies = list(result.scalars().all())
        matched = []
        for p in policies:
            applies = p.applies_to or {}
            if not applies or applies.get("priority") == priority or applies.get("priority") is None:
                matched.append(p)
        return matched
