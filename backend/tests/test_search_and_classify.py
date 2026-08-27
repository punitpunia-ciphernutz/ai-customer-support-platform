"""Phase E/F: search API + classify persistence."""

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import Organization
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.ai.application.ai_service import AIService
from app.modules.ai.domain.models import AIRun, AIRunStatus, AIRunType
from app.modules.ai.domain.schemas import IntentLabel
from app.modules.ai.infrastructure.llm.providers import EchoLLMProvider
from app.modules.knowledge.application.ingestion_service import IngestionService
from app.modules.knowledge.domain.models import IngestionStatus, KnowledgeSource, KnowledgeSourceType
from app.modules.knowledge.infrastructure.embeddings import OfflineSemanticEmbeddingProvider
from app.modules.knowledge.infrastructure.loaders import LoadedContent
from app.modules.knowledge.infrastructure.vectorstore import PgVectorRetriever


@pytest.mark.asyncio
async def test_retriever_returns_password_chunk() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        source = KnowledgeSource(
            organization_id=org_id,
            name="Search FAQ",
            type=KnowledgeSourceType.TEXT,
            status=IngestionStatus.PENDING,
            configuration={},
        )
        session.add(source)
        await session.flush()
        service = IngestionService(session, embedding_provider=OfflineSemanticEmbeddingProvider())
        doc = await service.create_pending_document(source=source, title="Password Reset", content="x")
        faq = "How do I reset my password? Use the Forgot Password link on the login page."
        await service.ingest_loaded_content(
            doc.id, LoadedContent(title="Password Reset", text=faq, metadata={"source_type": "TEXT"})
        )
        hits = await PgVectorRetriever(session, embedding_provider=OfflineSemanticEmbeddingProvider()).search(
            "How do I reset my password?",
            organization_id=org_id,
            top_k=3,
        )
        assert hits
        assert any("password" in h.content.lower() for h in hits)
        await session.rollback()


@pytest.mark.asyncio
async def test_ai_service_persists_classification_run() -> None:
    async with AsyncSessionLocal() as session:
        classification, run = await AIService(session, llm=EchoLLMProvider()).classify(
            "I cannot log into my account"
        )
        assert classification.intent == IntentLabel.ACCOUNT_ACCESS
        assert run.type == AIRunType.CLASSIFICATION
        assert run.status == AIRunStatus.SUCCEEDED
        assert run.output is not None
        stored = await session.get(AIRun, run.id)
        assert stored is not None
        await session.rollback()
