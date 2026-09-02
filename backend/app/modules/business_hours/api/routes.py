from datetime import date, time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_db
from app.modules.auth.permissions import AI_READ, AI_WRITE
from app.modules.business_hours.domain.models import BusinessHoliday, BusinessHours, BusinessHoursSchedule

router = APIRouter(prefix="/business-hours", tags=["business-hours"])


class ScheduleItem(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    open_time: str | None = None
    close_time: str | None = None
    closed: bool = False


class HolidayItem(BaseModel):
    id: str | None = None
    date: date
    name: str


class BusinessHoursCreate(BaseModel):
    name: str = "Support Hours"
    timezone: str = "UTC"
    is_default: bool = True
    schedule: list[ScheduleItem] = Field(default_factory=list)


class BusinessHoursUpdate(BaseModel):
    name: str | None = None
    timezone: str | None = None
    schedule: list[ScheduleItem] | None = None


class BusinessHoursOut(BaseModel):
    id: str
    name: str
    timezone: str
    is_default: bool
    schedule: list[ScheduleItem]
    holidays: list[HolidayItem]

    model_config = {"from_attributes": True}


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    parts = value.split(":")
    return time(int(parts[0]), int(parts[1]))


def _format_time(value: time | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%H:%M")


def _to_out(bh: BusinessHours) -> BusinessHoursOut:
    return BusinessHoursOut(
        id=bh.id,
        name=bh.name,
        timezone=bh.timezone,
        is_default=bh.is_default,
        schedule=[
            ScheduleItem(
                day_of_week=s.day_of_week,
                open_time=_format_time(s.open_time),
                close_time=_format_time(s.close_time),
                closed=s.closed,
            )
            for s in bh.schedules
        ],
        holidays=[HolidayItem(id=h.id, date=h.date, name=h.name) for h in bh.holidays],
    )


@router.get("", response_model=list[BusinessHoursOut])
async def list_business_hours(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_READ)),
):
    result = await db.execute(select(BusinessHours).where(BusinessHours.organization_id == user.organization_id))
    return [_to_out(bh) for bh in result.scalars().all()]


@router.post("", response_model=BusinessHoursOut, status_code=status.HTTP_201_CREATED)
async def create_business_hours(
    body: BusinessHoursCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_WRITE)),
):
    bh = BusinessHours(
        organization_id=user.organization_id,
        name=body.name,
        timezone=body.timezone,
        is_default=body.is_default,
    )
    db.add(bh)
    await db.flush()
    for item in body.schedule:
        db.add(
            BusinessHoursSchedule(
                business_hours_id=bh.id,
                day_of_week=item.day_of_week,
                open_time=_parse_time(item.open_time),
                close_time=_parse_time(item.close_time),
                closed=item.closed,
            )
        )
    await db.commit()
    await db.refresh(bh)
    return _to_out(bh)


@router.patch("/{business_hours_id}", response_model=BusinessHoursOut)
async def update_business_hours(
    business_hours_id: str,
    body: BusinessHoursUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_WRITE)),
):
    bh = await db.scalar(
        select(BusinessHours).where(
            BusinessHours.id == business_hours_id,
            BusinessHours.organization_id == user.organization_id,
        )
    )
    if bh is None:
        raise HTTPException(status_code=404, detail="Business hours not found")
    if body.name is not None:
        bh.name = body.name
    if body.timezone is not None:
        bh.timezone = body.timezone
    if body.schedule is not None:
        for s in list(bh.schedules):
            await db.delete(s)
        for item in body.schedule:
            db.add(
                BusinessHoursSchedule(
                    business_hours_id=bh.id,
                    day_of_week=item.day_of_week,
                    open_time=_parse_time(item.open_time),
                    close_time=_parse_time(item.close_time),
                    closed=item.closed,
                )
            )
    await db.commit()
    await db.refresh(bh)
    return _to_out(bh)


@router.get("/{business_hours_id}/holidays", response_model=list[HolidayItem])
async def list_holidays(
    business_hours_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_READ)),
):
    bh = await db.scalar(
        select(BusinessHours).where(
            BusinessHours.id == business_hours_id,
            BusinessHours.organization_id == user.organization_id,
        )
    )
    if bh is None:
        raise HTTPException(status_code=404, detail="Business hours not found")
    return [HolidayItem(id=h.id, date=h.date, name=h.name) for h in bh.holidays]


@router.post("/{business_hours_id}/holidays", response_model=HolidayItem, status_code=status.HTTP_201_CREATED)
async def add_holiday(
    business_hours_id: str,
    body: HolidayItem,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_WRITE)),
):
    bh = await db.scalar(
        select(BusinessHours).where(
            BusinessHours.id == business_hours_id,
            BusinessHours.organization_id == user.organization_id,
        )
    )
    if bh is None:
        raise HTTPException(status_code=404, detail="Business hours not found")
    holiday = BusinessHoliday(business_hours_id=bh.id, date=body.date, name=body.name)
    db.add(holiday)
    await db.commit()
    await db.refresh(holiday)
    return HolidayItem(id=holiday.id, date=body.date, name=body.name)


@router.delete("/{business_hours_id}/holidays/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_holiday(
    business_hours_id: str,
    holiday_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_WRITE)),
):
    holiday = await db.scalar(
        select(BusinessHoliday).where(BusinessHoliday.id == holiday_id, BusinessHoliday.business_hours_id == business_hours_id)
    )
    if holiday is None:
        raise HTTPException(status_code=404, detail="Holiday not found")
    await db.delete(holiday)
    await db.commit()
