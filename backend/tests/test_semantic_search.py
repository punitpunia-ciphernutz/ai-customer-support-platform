"""Semantic multi-document retrieval + LangChain wiring."""

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import Organization
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.knowledge.application.ingestion_service import IngestionService
from app.modules.knowledge.domain.models import IngestionStatus, KnowledgeSource, KnowledgeSourceType
from app.modules.knowledge.infrastructure.embeddings import OfflineSemanticEmbeddingProvider
from app.modules.knowledge.infrastructure.langchain import LangChainEmbeddingAdapter
from app.modules.knowledge.infrastructure.loaders import LoadedContent
from app.modules.knowledge.infrastructure.vectorstore import PgVectorRetriever


@pytest.mark.asyncio
async def test_multi_document_semantic_ranking() -> None:
    """Password query must rank password FAQ above billing FAQ."""
    provider = OfflineSemanticEmbeddingProvider(dimensions=1536)
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        source = KnowledgeSource(
            organization_id=org_id,
            name="Multi FAQ",
            type=KnowledgeSourceType.TEXT,
            status=IngestionStatus.PENDING,
            configuration={},
        )
        session.add(source)
        await session.flush()
        service = IngestionService(session, embedding_provider=provider)

        pwd = await service.create_pending_document(source=source, title="Password Reset", content="x")
        await service.ingest_loaded_content(
            pwd.id,
            LoadedContent(
                title="Password Reset",
                text=(
                    "How do I reset my password? Use the Forgot Password link on the login page "
                    "and follow the email instructions to regain account access."
                ),
                metadata={"source_type": "TEXT"},
            ),
        )

        bill = await service.create_pending_document(source=source, title="Billing FAQ", content="x")
        await service.ingest_loaded_content(
            bill.id,
            LoadedContent(
                title="Billing FAQ",
                text=(
                    "How do I update my billing address? Open Settings, choose Billing, "
                    "and edit your invoice mailing address for payment receipts."
                ),
                metadata={"source_type": "TEXT"},
            ),
        )

        hits = await PgVectorRetriever(session, embedding_provider=provider).search(
            "How do I reset my password?",
            organization_id=org_id,
            top_k=20,
        )
        by_id = {h.document_id: h for h in hits}
        assert pwd.id in by_id
        assert bill.id in by_id
        assert by_id[pwd.id].score > by_id[bill.id].score
        assert "password" in by_id[pwd.id].content.lower()
        await session.rollback()


@pytest.mark.asyncio
async def test_langchain_embedding_adapter() -> None:
    provider = OfflineSemanticEmbeddingProvider(dimensions=64)
    adapter = LangChainEmbeddingAdapter(provider)
    docs = await adapter.aembed_documents(["reset password", "reset password", "billing invoice"])
    assert docs[0] == docs[1]
    assert docs[0] != docs[2]
    query = await adapter.aembed_query("reset password")
    assert query == docs[0]
