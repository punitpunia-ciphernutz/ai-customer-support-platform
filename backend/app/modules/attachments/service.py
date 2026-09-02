from __future__ import annotations

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
