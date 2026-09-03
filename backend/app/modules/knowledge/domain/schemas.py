from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl

from app.modules.knowledge.domain.models import IngestionStatus, KnowledgeSourceType


class KnowledgeSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: KnowledgeSourceType
    configuration: dict[str, Any] = Field(default_factory=dict)


class KnowledgeSourceOut(BaseModel):
    id: str
    organization_id: str
    name: str
    type: KnowledgeSourceType
    status: IngestionStatus
    configuration: dict[str, Any]
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TextDocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    content: str = Field(min_length=1)


class URLDocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    url: HttpUrl


class DocumentOut(BaseModel):
    id: str
    knowledge_source_id: str
    title: str
    source_url: str | None
    content_hash: str | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    status: IngestionStatus
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class DocumentChunkOut(BaseModel):
    id: str
    document_id: str
    content: str
    chunk_index: int
    token_count: int | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int | None = Field(default=None, ge=1, le=50)


class KnowledgeSearchResult(BaseModel):
    document_id: str
    title: str
    content: str
    score: float
    chunk_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeSearchResponse(BaseModel):
    results: list[KnowledgeSearchResult]


class DocumentDetailOut(DocumentOut):
    content: str | None = None


class TextDocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=512)
    content: str | None = Field(default=None, min_length=1)


class DocumentAccepted(BaseModel):
    document: DocumentOut
    job_queued: bool = True
