from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_db
from app.modules.auth.permissions import AI_READ, AI_WRITE
from app.modules.notifications.application.service import NotificationService
from app.modules.notifications.domain.models import Notification, NotificationPreference

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: str
    event_type: str
    title: str
    body: str
    read_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PreferenceOut(BaseModel):
    event_type: str
    in_app: bool
    email: bool
    enabled: bool


class PreferenceUpdate(BaseModel):
    preferences: list[PreferenceOut]


@router.get("", response_model=list[NotificationOut])
async def list_notifications(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_READ)),
):
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(100)
    )
    return list(result.scalars().all())


@router.patch("/{notification_id}/read", response_model=NotificationOut)
async def mark_read(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_READ)),
):
    notification = await db.scalar(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id)
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.read_at = datetime.utcnow()
    await db.commit()
    await db.refresh(notification)
    return notification


preferences_router = APIRouter(prefix="/notification-preferences", tags=["notifications"])


@preferences_router.get("", response_model=list[PreferenceOut])
async def get_preferences(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_READ)),
):
    await NotificationService(db).ensure_default_preferences(user.id)
    await db.commit()
    result = await db.execute(select(NotificationPreference).where(NotificationPreference.user_id == user.id))
    return [
        PreferenceOut(event_type=p.event_type, in_app=p.in_app, email=p.email, enabled=p.enabled)
        for p in result.scalars().all()
    ]


@preferences_router.patch("", response_model=list[PreferenceOut])
async def update_preferences(
    body: PreferenceUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_WRITE)),
):
    for pref in body.preferences:
        row = await db.scalar(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user.id,
                NotificationPreference.event_type == pref.event_type,
            )
        )
        if row is None:
            row = NotificationPreference(user_id=user.id, event_type=pref.event_type)
            db.add(row)
        row.in_app = pref.in_app
        row.email = pref.email
        row.enabled = pref.enabled
    await db.commit()
    result = await db.execute(select(NotificationPreference).where(NotificationPreference.user_id == user.id))
    return [
        PreferenceOut(event_type=p.event_type, in_app=p.in_app, email=p.email, enabled=p.enabled)
        for p in result.scalars().all()
    ]
