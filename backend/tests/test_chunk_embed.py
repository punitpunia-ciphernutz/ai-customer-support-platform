"""Update chunk/embed tests for OfflineSemantic + Gemini factory."""

import pytest

from app.modules.knowledge.infrastructure.embeddings import (
    OfflineSemanticEmbeddingProvider,
    get_embedding_provider,
)
from app.modules.knowledge.infrastructure.parsers import TokenChunker, get_default_chunker


def test_token_chunker_overlap_and_size() -> None:
    chunker = TokenChunker(chunk_size=10, chunk_overlap=3)
    text = " ".join(f"w{i}" for i in range(25))
    chunks = chunker.chunk(text, metadata={"doc": "x"})
    assert len(chunks) >= 3
    assert chunks[0].index == 0
    assert chunks[0].metadata["doc"] == "x"
    # Overlap: shared tokens between adjacent chunks
    first_tokens = set(chunks[0].content.split())
    second_tokens = set(chunks[1].content.split())
    assert first_tokens & second_tokens


def test_token_chunker_rejects_bad_config() -> None:
    with pytest.raises(ValueError):
        TokenChunker(chunk_size=10, chunk_overlap=10)


@pytest.mark.asyncio
async def test_offline_semantic_embedding_provider_dimensions() -> None:
    provider = OfflineSemanticEmbeddingProvider(dimensions=1536)
    docs = await provider.embed_documents(["hello world", "hello world", "other"])
    assert len(docs) == 3
    assert len(docs[0]) == 1536
    assert docs[0] == docs[1]
    assert docs[0] != docs[2]
    # Shared vocabulary → higher similarity than unrelated strings
    query = await provider.embed_query("hello world reset password")
    pwd = await provider.embed_query("reset password instructions")
    billing = await provider.embed_query("invoice billing address payment")

    def cosine(a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b, strict=True))

    assert cosine(query, pwd) > cosine(query, billing)


def test_default_factories() -> None:
    chunker = get_default_chunker()
    assert chunker.chunk_size == 600
    assert chunker.chunk_overlap == 80
    provider = get_embedding_provider()
    assert isinstance(provider, OfflineSemanticEmbeddingProvider)
