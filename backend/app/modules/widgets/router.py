from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_db
from app.modules.auth.permissions import SETTINGS_READ, SETTINGS_WRITE
from app.modules.widgets.schemas import (
    EmbedSnippetOut,
    PreviewTokenOut,
    WidgetCreate,
    WidgetOut,
    WidgetUpdate,
)
from app.modules.widgets.service import WidgetService

router = APIRouter(prefix="/widgets", tags=["widgets"])


@router.get("", response_model=list[WidgetOut])
async def list_widgets(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(SETTINGS_READ)),
):
    return await WidgetService(db).list_widgets(user.organization_id)


@router.post("", response_model=WidgetOut, status_code=201)
async def create_widget(
    body: WidgetCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(SETTINGS_WRITE)),
):
    return await WidgetService(db).create_widget(user.organization_id, body)


@router.get("/{widget_id}", response_model=WidgetOut)
async def get_widget(
    widget_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(SETTINGS_READ)),
):
    return await WidgetService(db).get_widget(user.organization_id, widget_id)


@router.patch("/{widget_id}", response_model=WidgetOut)
async def update_widget(
    widget_id: str,
    body: WidgetUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(SETTINGS_WRITE)),
):
    return await WidgetService(db).update_widget(user.organization_id, widget_id, body)


@router.delete("/{widget_id}", status_code=204)
async def delete_widget(
    widget_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(SETTINGS_WRITE)),
):
    await WidgetService(db).delete_widget(user.organization_id, widget_id)


@router.get("/{widget_id}/embed-snippet", response_model=EmbedSnippetOut)
async def get_embed_snippet(
    widget_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(SETTINGS_READ)),
):
    widget = await WidgetService(db).get_widget(user.organization_id, widget_id)
    return WidgetService(db).build_embed_snippet(widget)


@router.post("/{widget_id}/preview-token", response_model=PreviewTokenOut)
async def create_preview_token(
    widget_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(SETTINGS_READ)),
):
    return await WidgetService(db).create_preview_token_for(
        user.organization_id, widget_id, user.id
    )
