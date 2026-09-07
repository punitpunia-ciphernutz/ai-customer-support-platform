from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_db
from app.modules.attachments.service import AttachmentService
from app.modules.auth.permissions import CONVERSATIONS_READ, CONVERSATIONS_WRITE
from app.modules.channels.schemas import AttachmentOut

router = APIRouter(prefix="/attachments", tags=["attachments"])


def _content_disposition(filename: str) -> str:
    # ASCII fallback + RFC 5987 for non-ASCII names
    safe = "".join(c if 32 <= ord(c) < 127 and c not in {'"', "\\"} else "_" for c in filename) or "download"
    encoded = quote(filename)
    return f'attachment; filename="{safe}"; filename*=UTF-8\'\'{encoded}'


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


@router.get("/{attachment_id}/download")
async def download_attachment(
    attachment_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_READ)),
):
    service = AttachmentService(db)
    attachment = await service.get(user.organization_id, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    try:
        data = await service.read_bytes(attachment)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Attachment file missing") from exc
    except OSError as exc:
        raise HTTPException(status_code=404, detail="Attachment file missing") from exc
    return Response(
        content=data,
        media_type=attachment.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": _content_disposition(attachment.filename),
            "Content-Length": str(len(data)),
        },
    )
