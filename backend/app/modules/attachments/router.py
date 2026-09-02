from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_db
from app.modules.attachments.service import AttachmentService
from app.modules.auth.permissions import CONVERSATIONS_READ, CONVERSATIONS_WRITE
from app.modules.channels.schemas import AttachmentOut

router = APIRouter(prefix="/attachments", tags=["attachments"])


@router.post("", response_model=AttachmentOut, status_code=201)
async def upload_attachment(
    file: UploadFile = File(...),
    message_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_WRITE)),
):
    data = await file.read()
    attachment = await AttachmentService(db).upload(
        organization_id=user.organization_id,
        filename=file.filename or "attachment",
        mime_type=file.content_type or "application/octet-stream",
        data=data,
        message_id=message_id,
    )
    out = AttachmentOut.model_validate(attachment)
    out.download_url = await AttachmentService(db).get_download_url(attachment)
    return out


@router.get("/{attachment_id}", response_model=AttachmentOut)
async def get_attachment(
    attachment_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_READ)),
):
    attachment = await AttachmentService(db).get(user.organization_id, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    out = AttachmentOut.model_validate(attachment)
    out.download_url = await AttachmentService(db).get_download_url(attachment)
    return out
