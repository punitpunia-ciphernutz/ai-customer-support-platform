"""Phase C: loaders, normalize, content_hash; ingest pipeline with hash embeddings."""

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import Organization
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.knowledge.application.ingestion_service import IngestionService
from app.modules.knowledge.domain.models import DocumentChunk, IngestionStatus, KnowledgeSource, KnowledgeSourceType
from app.modules.knowledge.infrastructure.embeddings import HashEmbeddingProvider
from app.modules.knowledge.infrastructure.loaders import LoadedContent, PDFLoader, TextLoader
from app.modules.knowledge.infrastructure.parsers import content_hash, html_to_text, normalize_text


def test_normalize_and_hash() -> None:
    text = normalize_text("Hello   world\r\n\r\n\r\nAgain")
    assert "  " not in text
    assert content_hash(text) == content_hash(text)
    assert content_hash(text) != content_hash(text + "x")


def test_html_to_text_strips_scripts() -> None:
    html = "<html><head><script>bad()</script></head><body><h1>Title</h1><p>Hello</p></body></html>"
    text = html_to_text(html)
    assert "bad()" not in text
    assert "Title" in text
    assert "Hello" in text


@pytest.mark.asyncio
async def test_text_loader() -> None:
    loaded = await TextLoader("  reset password  ", title="FAQ").load()
    assert loaded.title == "FAQ"
    assert loaded.text == "reset password"


@pytest.mark.asyncio
async def test_pdf_loader_roundtrip() -> None:
    from io import BytesIO

    from pypdf import PdfWriter

    buffer = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(buffer)
    loaded = await PDFLoader(buffer.getvalue(), title="Blank").load()
    assert loaded.title == "Blank"
    assert loaded.metadata["source_type"] == "PDF"


@pytest.mark.asyncio
async def test_ingest_text_document_creates_chunks() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        source = KnowledgeSource(
            organization_id=org_id,
            name="Test FAQ",
            type=KnowledgeSourceType.TEXT,
            status=IngestionStatus.PENDING,
            configuration={},
        )
        session.add(source)
        await session.flush()

        service = IngestionService(session, embedding_provider=HashEmbeddingProvider())
        document = await service.create_pending_document(
            source=source,
            title="Password Reset",
            content="placeholder",
        )
        faq = (
            "How do I reset my password? Go to settings, click Forgot Password, "
            "and follow the email link. You can also contact support for account access help."
        )
        loaded = LoadedContent(title="Password Reset", text=faq, metadata={"source_type": "TEXT"})
        document = await service.ingest_loaded_content(document.id, loaded)
        assert document.status == IngestionStatus.COMPLETED
        assert document.content_hash == content_hash(faq)

        chunks = (
            await session.execute(select(DocumentChunk).where(DocumentChunk.document_id == document.id))
        ).scalars().all()
        assert len(chunks) >= 1
        assert chunks[0].embedding is not None
        assert chunks[0].metadata_["title"] == "Password Reset"

        before_ids = {c.id for c in chunks}
        document2 = await service.ingest_loaded_content(document.id, loaded)
        assert document2.status == IngestionStatus.COMPLETED
        after = (
            await session.execute(select(DocumentChunk).where(DocumentChunk.document_id == document.id))
        ).scalars().all()
        assert {c.id for c in after} == before_ids

        await session.rollback()
