from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import Attachment, ExternalMessage


class IdempotencyService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def is_processed(self, organization_id: str, provider: str, external_message_id: str) -> bool:
        result = await self.db.execute(
            select(ExternalMessage.id).where(
                ExternalMessage.organization_id == organization_id,
                ExternalMessage.provider == provider,
                ExternalMessage.external_message_id == external_message_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def record(
        self,
        organization_id: str,
        provider: str,
        external_message_id: str,
        message_id: str,
    ) -> ExternalMessage:
        record = ExternalMessage(
            organization_id=organization_id,
            provider=provider,
            external_message_id=external_message_id,
            message_id=message_id,
        )
        self.db.add(record)
        await self.db.flush()
        return record
