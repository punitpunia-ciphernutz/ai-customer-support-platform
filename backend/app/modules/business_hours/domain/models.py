"""Business hours persistence models."""

from datetime import date, datetime, time
from typing import Any
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Time, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base


class BusinessHours(Base):
    __tablename__ = "business_hours"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    schedules: Mapped[list["BusinessHoursSchedule"]] = relationship(
        back_populates="business_hours", cascade="all, delete-orphan", lazy="selectin"
    )
    holidays: Mapped[list["BusinessHoliday"]] = relationship(
        back_populates="business_hours", cascade="all, delete-orphan", lazy="selectin"
    )


class BusinessHoursSchedule(Base):
    __tablename__ = "business_hours_schedules"
    __table_args__ = (
        UniqueConstraint("business_hours_id", "day_of_week", name="uq_business_hours_day"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    business_hours_id: Mapped[str] = mapped_column(
        ForeignKey("business_hours.id"), nullable=False, index=True
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Monday .. 6=Sunday
    open_time: Mapped[time | None] = mapped_column(Time)
    close_time: Mapped[time | None] = mapped_column(Time)
    closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    business_hours: Mapped["BusinessHours"] = relationship(back_populates="schedules")


class BusinessHoliday(Base):
    __tablename__ = "business_holidays"
    __table_args__ = (
        UniqueConstraint("business_hours_id", "date", name="uq_business_holiday_date"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    business_hours_id: Mapped[str] = mapped_column(
        ForeignKey("business_hours.id"), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    business_hours: Mapped["BusinessHours"] = relationship(back_populates="holidays")
