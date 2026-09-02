from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_db
from app.infrastructure.email import get_email_provider
from app.modules.conversations.service import ConversationService

router = APIRouter(prefix="/webhooks/email", tags=["webhooks"])


@router.post("/inbound")
async def inbound_email_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    provider_name = headers.get("x-email-provider") or payload.get("provider") or "mock"
    provider = get_email_provider(provider_name)

    if not provider.verify(headers, body):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    parsed = provider.parse(payload)
    normalized = provider.normalize(parsed)

    org_id = (
        payload.get("organization_id")
        or headers.get("x-organization-id")
        or normalized.get("organization_id")
    )
    if not org_id:
        raise HTTPException(status_code=400, detail="organization_id required")

    service = ConversationService(db)
    conversation, message, created = await service.receive_inbound_email(
        organization_id=str(org_id),
        provider=provider.name,
        normalized=normalized,
    )
    await db.commit()
    return {
        "status": "ok",
        "duplicate": not created,
        "conversation_id": conversation.id,
        "message_id": message.id,
    }
