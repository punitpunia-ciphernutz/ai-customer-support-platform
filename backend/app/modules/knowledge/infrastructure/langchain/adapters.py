"""LangChain adapters — keep LangChain behind knowledge interfaces."""

from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, Field, PrivateAttr
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge.infrastructure.embeddings import EmbeddingProvider, get_embedding_provider


def _run_sync(coro):  # type: ignore[no-untyped-def]
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("Synchronous LangChain call is not supported inside a running event loop")


class LangChainEmbeddingAdapter(Embeddings):
    """Expose our EmbeddingProvider as a LangChain Embeddings instance."""

    def __init__(self, provider: EmbeddingProvider | None = None) -> None:
        self._provider = provider or get_embedding_provider()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return _run_sync(self.aembed_documents(texts))

    def embed_query(self, text: str) -> list[float]:
        return _run_sync(self.aembed_query(text))

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._provider.embed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        return await self._provider.embed_query(text)


class LangChainPgVectorRetriever(BaseRetriever):
    """LangChain BaseRetriever backed by pgvector similarity search."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    organization_id: str
    top_k: int = 5
    _db: AsyncSession = PrivateAttr()
    _embedding_provider: EmbeddingProvider = PrivateAttr()

    def __init__(
        self,
        *,
        db: AsyncSession,
        organization_id: str,
        embedding_provider: EmbeddingProvider | None = None,
        top_k: int = 5,
        **kwargs: Any,
    ) -> None:
        super().__init__(organization_id=organization_id, top_k=top_k, **kwargs)
        self._db = db
        self._embedding_provider = embedding_provider or get_embedding_provider()

    def _get_relevant_documents(
        self, query: str, *, run_manager: Any = None  # noqa: ARG002
    ) -> list[Document]:
        return _run_sync(self._aget_relevant_documents(query))

    async def _aget_relevant_documents(
        self, query: str, *, run_manager: Any = None  # noqa: ARG002
    ) -> list[Document]:
        from app.modules.knowledge.infrastructure.vectorstore.retriever import PgVectorRetriever

        hits = await PgVectorRetriever(
            self._db,
            embedding_provider=self._embedding_provider,
            default_top_k=self.top_k,
        ).search_pgvector(query, organization_id=self.organization_id, top_k=self.top_k)
        return [
            Document(
                page_content=hit.content,
                metadata={
                    "document_id": hit.document_id,
                    "chunk_id": hit.chunk_id,
                    "title": hit.title,
                    "score": hit.score,
                    **(hit.metadata or {}),
                },
            )
            for hit in hits
        ]
