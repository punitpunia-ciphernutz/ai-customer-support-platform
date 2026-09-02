from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.infrastructure.database.models import ChannelType, User
from app.infrastructure.database.session import get_db
from app.modules.auth.permissions import CONVERSATIONS_READ, CONVERSATIONS_WRITE
from app.modules.channels.schemas import ChannelConfigurationOut, ChannelConfigurationUpdate
from app.modules.channels.service import ChannelService

router = APIRouter(prefix="/channels", tags=["channels"])


@router.get("", response_model=list[ChannelConfigurationOut])
async def list_channels(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_READ)),
):
    return await ChannelService(db).list_channels(user.organization_id)


@router.get("/{channel}", response_model=ChannelConfigurationOut)
async def get_channel(
    channel: ChannelType,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_READ)),
):
    try:
        return await ChannelService(db).get_channel(user.organization_id, channel)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{channel}", response_model=ChannelConfigurationOut)
async def update_channel(
    channel: ChannelType,
    body: ChannelConfigurationUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_WRITE)),
):
    data = body.model_dump(exclude_unset=True)
    return await ChannelService(db).update_channel(user.organization_id, channel, **data)
