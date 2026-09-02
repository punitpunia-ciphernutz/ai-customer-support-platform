"""Day 6 business hours tests."""

from datetime import date, datetime, time, timezone

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import Organization
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.business_hours.application.service import BusinessHoursService
from app.modules.business_hours.domain.models import BusinessHoliday, BusinessHours, BusinessHoursSchedule


@pytest.mark.asyncio
async def test_business_hours_open_closed() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        bh = await session.scalar(select(BusinessHours).where(BusinessHours.organization_id == org_id))
        if bh is None:
            bh = BusinessHours(organization_id=org_id, name="Test", timezone="UTC", is_default=True)
            session.add(bh)
            await session.flush()
            for day in range(5):
                session.add(
                    BusinessHoursSchedule(
                        business_hours_id=bh.id,
                        day_of_week=day,
                        open_time=time(9, 0),
                        close_time=time(18, 0),
                    )
                )
            await session.commit()

        service = BusinessHoursService(session)
        monday_open = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
        monday_closed = datetime(2026, 9, 7, 20, 0, tzinfo=timezone.utc)
        assert await service.is_open(org_id, monday_open)
        assert not await service.is_open(org_id, monday_closed)


@pytest.mark.asyncio
async def test_business_hours_holiday() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        bh = BusinessHours(organization_id=org_id, name="Holiday Test", timezone="UTC", is_default=False)
        session.add(bh)
        await session.flush()
        session.add(
            BusinessHoursSchedule(
                business_hours_id=bh.id,
                day_of_week=0,
                open_time=time(9, 0),
                close_time=time(18, 0),
            )
        )
        session.add(BusinessHoliday(business_hours_id=bh.id, date=date(2026, 9, 7), name="Test Holiday"))
        await session.commit()
        await session.refresh(bh, ["schedules", "holidays"])

        service = BusinessHoursService(session)
        assert not service._is_open_for_hours(bh, datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc))
