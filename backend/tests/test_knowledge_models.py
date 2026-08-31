"""Phase A: knowledge models import and source CRUD smoke."""

from app.modules.knowledge.domain.models import (
    Document,
    DocumentChunk,
    EMBEDDING_DIMENSIONS,
    IngestionStatus,
    KnowledgeSource,
    KnowledgeSourceType,
)


def test_knowledge_models_exported() -> None:
    assert KnowledgeSource.__tablename__ == "knowledge_sources"
    assert Document.__tablename__ == "documents"
    assert DocumentChunk.__tablename__ == "document_chunks"
    assert EMBEDDING_DIMENSIONS == 1536
    assert KnowledgeSourceType.TEXT.value == "TEXT"
    assert IngestionStatus.PENDING.value == "PENDING"


def test_app_includes_knowledge_routes() -> None:
    from app.main import app

    paths = set(app.openapi()["paths"])
    assert "/api/v1/knowledge/sources" in paths
    assert "/api/v1/knowledge/documents/{document_id}" in paths
    assert "/api/v1/knowledge/documents/{document_id}/retry" in paths
    assert "/api/v1/knowledge/sources/{source_id}/retry" in paths
