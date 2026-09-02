"""Business hours application service."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.ai.application.ai_config_service import get_or_create_ai_config
from app.modules.business_hours.domain.models import BusinessHoliday, BusinessHours, BusinessHoursSchedule


class BusinessHoursService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_default(self, organization_id: str) -> BusinessHours | None:
        return await self.db.scalar(
            select(BusinessHours)
            .where(BusinessHours.organization_id == organization_id, BusinessHours.is_default.is_(True))
            .options(
                selectinload(BusinessHours.schedules),  # type: ignore[arg-type]
                selectinload(BusinessHours.holidays),  # type: ignore[arg-type]
            )
        )

    async def is_open(self, organization_id: str, dt: datetime | None = None) -> bool:
        hours = await self.get_default(organization_id)
        if hours is None:
            return await self._fallback_ai_config_hours(organization_id, dt)
        return self._is_open_for_hours(hours, dt or datetime.now(tz=ZoneInfo("UTC")))

    async def next_open_time(self, organization_id: str, dt: datetime | None = None) -> datetime | None:
        hours = await self.get_default(organization_id)
        if hours is None:
            return None
        current = dt or datetime.now(tz=ZoneInfo("UTC"))
        tz = ZoneInfo(hours.timezone)
        local = current.astimezone(tz)
        for offset in range(0, 366):
            day = local.date() + timedelta(days=offset)
            if self._is_holiday(hours, day):
                continue
            schedule = self._schedule_for_day(hours, day.weekday())
            if schedule is None or schedule.closed or not schedule.open_time:
                continue
            open_dt = datetime.combine(day, schedule.open_time, tzinfo=tz)
            if offset == 0 and local >= open_dt:
                if schedule.close_time and local.time() < schedule.close_time:
                    return local
                continue
            return open_dt
        return None

    async def next_close_time(self, organization_id: str, dt: datetime | None = None) -> datetime | None:
        hours = await self.get_default(organization_id)
        if hours is None:
            return None
        current = dt or datetime.now(tz=ZoneInfo("UTC"))
        if not self._is_open_for_hours(hours, current):
            return None
        tz = ZoneInfo(hours.timezone)
        local = current.astimezone(tz)
        schedule = self._schedule_for_day(hours, local.weekday())
        if schedule is None or schedule.closed or not schedule.close_time:
            return None
        return datetime.combine(local.date(), schedule.close_time, tzinfo=tz)

    def add_business_minutes(self, organization_id: str, hours: BusinessHours, start: datetime, minutes: int) -> datetime:
        """Add business minutes using weekly schedule (holidays skipped)."""
        tz = ZoneInfo(hours.timezone)
        current = start.astimezone(tz)
        remaining = minutes
        safety = 0
        while remaining > 0 and safety < 10000:
            safety += 1
            if self._is_holiday(hours, current.date()):
                current = datetime.combine(current.date() + timedelta(days=1), time(0, 0), tzinfo=tz)
                continue
            schedule = self._schedule_for_day(hours, current.weekday())
            if schedule is None or schedule.closed or not schedule.open_time or not schedule.close_time:
                current = datetime.combine(current.date() + timedelta(days=1), time(0, 0), tzinfo=tz)
                continue
            open_dt = datetime.combine(current.date(), schedule.open_time, tzinfo=tz)
            close_dt = datetime.combine(current.date(), schedule.close_time, tzinfo=tz)
            if current < open_dt:
                current = open_dt
            if current >= close_dt:
                current = datetime.combine(current.date() + timedelta(days=1), time(0, 0), tzinfo=tz)
                continue
            available = int((close_dt - current).total_seconds() // 60)
            if remaining <= available:
                return current + timedelta(minutes=remaining)
            remaining -= available
            current = datetime.combine(current.date() + timedelta(days=1), time(0, 0), tzinfo=tz)
        return current

    def _is_open_for_hours(self, hours: BusinessHours, dt: datetime) -> bool:
        tz = ZoneInfo(hours.timezone)
        local = dt.astimezone(tz)
        if self._is_holiday(hours, local.date()):
            return False
        schedule = self._schedule_for_day(hours, local.weekday())
        if schedule is None or schedule.closed or not schedule.open_time or not schedule.close_time:
            return False
        t = local.time()
        return schedule.open_time <= t < schedule.close_time

    def _is_holiday(self, hours: BusinessHours, d: date) -> bool:
        holidays: list[BusinessHoliday] = getattr(hours, "holidays", []) or []
        return any(h.date == d for h in holidays)

    def _schedule_for_day(self, hours: BusinessHours, day_of_week: int) -> BusinessHoursSchedule | None:
        schedules: list[BusinessHoursSchedule] = getattr(hours, "schedules", []) or []
        for s in schedules:
            if s.day_of_week == day_of_week:
                return s
        return None

    async def _fallback_ai_config_hours(self, organization_id: str, dt: datetime | None) -> bool:
        config = await get_or_create_ai_config(self.db, organization_id)
        hours = config.business_hours or {}
        schedule = hours.get("schedule") or {}
        if not schedule:
            return True
        now = (dt or datetime.now(tz=ZoneInfo("UTC"))).astimezone(ZoneInfo("UTC"))
        day = now.strftime("%A").lower()
        day_schedule = schedule.get(day)
        if not day_schedule:
            return False
        start = day_schedule.get("start", "09:00")
        end = day_schedule.get("end", "18:00")
        current = now.strftime("%H:%M")
        return start <= current <= end
