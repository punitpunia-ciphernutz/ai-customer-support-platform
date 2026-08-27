"""Phase B: chunker and embedding provider."""

import pytest

from app.modules.knowledge.infrastructure.embeddings import (
    HashEmbeddingProvider,
    get_embedding_provider,
)
from app.modules.knowledge.infrastructure.parsers import TokenChunker, get_default_chunker


def test_token_chunker_overlap_and_size() -> None:
    chunker = TokenChunker(chunk_size=10, chunk_overlap=3)
    text = " ".join(f"w{i}" for i in range(25))
    chunks = chunker.chunk(text, metadata={"doc": "x"})
    assert len(chunks) >= 3
    assert chunks[0].token_count == 10
    assert chunks[0].index == 0
    assert chunks[0].metadata["doc"] == "x"
    # Overlap: last 3 tokens of chunk 0 appear at start of chunk 1
    first_tokens = chunks[0].content.split()
    second_tokens = chunks[1].content.split()
    assert first_tokens[-3:] == second_tokens[:3]


def test_token_chunker_rejects_bad_config() -> None:
    with pytest.raises(ValueError):
        TokenChunker(chunk_size=10, chunk_overlap=10)


@pytest.mark.asyncio
async def test_hash_embedding_provider_dimensions() -> None:
    provider = HashEmbeddingProvider(dimensions=1536)
    docs = await provider.embed_documents(["hello world", "hello world", "other"])
    assert len(docs) == 3
    assert len(docs[0]) == 1536
    assert docs[0] == docs[1]
    assert docs[0] != docs[2]
    query = await provider.embed_query("hello world")
    assert query == docs[0]


def test_default_factories() -> None:
    chunker = get_default_chunker()
    assert chunker.chunk_size == 600
    assert chunker.chunk_overlap == 80
    provider = get_embedding_provider()
    assert isinstance(provider, HashEmbeddingProvider)
