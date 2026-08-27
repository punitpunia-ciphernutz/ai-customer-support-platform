"""Org-scoped knowledge source / document queries."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.knowledge.domain.models import Document, IngestionStatus, KnowledgeSource, KnowledgeSourceType


class KnowledgeService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_sources(self, organization_id: str) -> list[KnowledgeSource]:
        result = await self.db.execute(
            select(KnowledgeSource)
            .where(KnowledgeSource.organization_id == organization_id)
            .order_by(KnowledgeSource.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_source(self, organization_id: str, source_id: str) -> KnowledgeSource | None:
        result = await self.db.execute(
            select(KnowledgeSource).where(
                KnowledgeSource.id == source_id,
                KnowledgeSource.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_source_with_documents(
        self, organization_id: str, source_id: str
    ) -> KnowledgeSource | None:
        result = await self.db.execute(
            select(KnowledgeSource)
            .options(selectinload(KnowledgeSource.documents))
            .where(
                KnowledgeSource.id == source_id,
                KnowledgeSource.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_source(
        self,
        organization_id: str,
        name: str,
        source_type: KnowledgeSourceType,
        configuration: dict | None = None,
    ) -> KnowledgeSource:
        source = KnowledgeSource(
            organization_id=organization_id,
            name=name,
            type=source_type,
            status=IngestionStatus.PENDING,
            configuration=configuration or {},
        )
        self.db.add(source)
        await self.db.flush()
        await self.db.refresh(source)
        return source

    async def list_documents(self, organization_id: str, source_id: str) -> list[Document]:
        result = await self.db.execute(
            select(Document)
            .join(KnowledgeSource)
            .where(
                Document.knowledge_source_id == source_id,
                KnowledgeSource.organization_id == organization_id,
            )
            .order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_document(self, organization_id: str, document_id: str) -> Document | None:
        result = await self.db.execute(
            select(Document)
            .join(KnowledgeSource)
            .where(
                Document.id == document_id,
                KnowledgeSource.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def delete_document(self, organization_id: str, document_id: str) -> bool:
        document = await self.get_document(organization_id, document_id)
        if document is None:
            return False
        await self.db.delete(document)
        await self.db.flush()
        return True
