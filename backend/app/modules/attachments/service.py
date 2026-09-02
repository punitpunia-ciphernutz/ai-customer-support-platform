from __future__ import annotations

import base64
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import Attachment, Conversation, Message
from app.infrastructure.storage import get_object_storage


class AttachmentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.storage = get_object_storage()

    async def upload(
        self,
        *,
        organization_id: str,
        filename: str,
        mime_type: str,
        data: bytes,
        message_id: str | None = None,
    ) -> Attachment:
        if message_id:
            msg = await self.db.get(Message, message_id)
            if msg is None:
                raise ValueError("Message not found")
            conv = await self.db.get(Conversation, msg.conversation_id)
            if conv is None or conv.organization_id != organization_id:
                raise ValueError("Message not found")

        storage_key = f"{organization_id}/attachments/{uuid4()}/{filename}"
        await self.storage.upload(storage_key, data, mime_type)
        attachment = Attachment(
            message_id=message_id,
            filename=filename,
            mime_type=mime_type,
            size=len(data),
            storage_key=storage_key,
            metadata_={"pending": True} if not message_id else {},
        )
        self.db.add(attachment)
        await self.db.flush()
        await self.db.refresh(attachment)
        return attachment

    async def get(self, organization_id: str, attachment_id: str) -> Attachment | None:
        attachment = await self.db.get(Attachment, attachment_id)
        if attachment is None:
            return None
        if attachment.message_id:
            msg = await self.db.get(Message, attachment.message_id)
            if msg is None:
                return None
            conv = await self.db.get(Conversation, msg.conversation_id)
            if conv is None or conv.organization_id != organization_id:
                return None
        return attachment

    async def link_to_message(self, attachment_id: str, message_id: str) -> Attachment:
        attachment = await self.db.get(Attachment, attachment_id)
        if attachment is None:
            raise ValueError("Attachment not found")
        attachment.message_id = message_id
        meta = dict(attachment.metadata_ or {})
        meta.pop("pending", None)
        attachment.metadata_ = meta
        await self.db.flush()
        await self.db.refresh(attachment)
        return attachment

    async def get_download_url(self, attachment: Attachment) -> str:
        return await self.storage.generate_url(attachment.storage_key)

    async def list_for_message(self, message_id: str) -> list[Attachment]:
        result = await self.db.execute(
            select(Attachment).where(Attachment.message_id == message_id)
        )
        return list(result.scalars().all())

    async def list_for_messages(self, message_ids: list[str]) -> dict[str, list[Attachment]]:
        if not message_ids:
            return {}
        result = await self.db.execute(
            select(Attachment).where(Attachment.message_id.in_(message_ids))
        )
        grouped: dict[str, list[Attachment]] = {}
        for attachment in result.scalars().all():
            if attachment.message_id:
                grouped.setdefault(attachment.message_id, []).append(attachment)
        return grouped

    async def store_inbound(
        self,
        *,
        organization_id: str,
        message_id: str,
        items: list[dict[str, Any]],
    ) -> list[Attachment]:
        stored: list[Attachment] = []
        for item in items:
            filename = str(item.get("filename") or item.get("name") or "attachment")
            mime_type = str(item.get("mime_type") or item.get("content_type") or "application/octet-stream")
            raw = item.get("data")
            if raw is None and item.get("content_base64"):
                raw = base64.b64decode(str(item["content_base64"]))
            if raw is None and item.get("content"):
                content = item["content"]
                raw = content if isinstance(content, (bytes, bytearray)) else str(content).encode()
            if raw is None:
                continue
            data = bytes(raw)
            attachment = await self.upload(
                organization_id=organization_id,
                filename=filename,
                mime_type=mime_type,
                data=data,
                message_id=message_id,
            )
            stored.append(attachment)
        return stored

    async def load_for_send(self, attachment_ids: list[str]) -> list[Attachment]:
        if not attachment_ids:
            return []
        result = await self.db.execute(select(Attachment).where(Attachment.id.in_(attachment_ids)))
        return list(result.scalars().all())

    async def build_outbound_payload(self, attachment_ids: list[str]) -> list[dict[str, Any]]:
        attachments = await self.load_for_send(attachment_ids)
        payload: list[dict[str, Any]] = []
        for attachment in attachments:
            data = await self.storage.download(attachment.storage_key)
            payload.append(
                {
                    "filename": attachment.filename,
                    "mime_type": attachment.mime_type,
                    "content_base64": base64.b64encode(data).decode("ascii"),
                }
            )
        return payload
