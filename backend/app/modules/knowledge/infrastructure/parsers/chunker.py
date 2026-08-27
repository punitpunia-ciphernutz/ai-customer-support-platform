"""Token-oriented text chunking with configurable size and overlap."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TextChunk:
    content: str
    index: int
    token_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


class Chunker(ABC):
    @abstractmethod
    def chunk(self, text: str, *, metadata: dict[str, Any] | None = None) -> list[TextChunk]:
        raise NotImplementedError


class TokenChunker(Chunker):
    """Approximate token chunking by whitespace tokens (configurable size/overlap)."""

    def __init__(self, chunk_size: int = 600, chunk_overlap: int = 80) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size must be >= 1")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be >= 0")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be < chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, text: str, *, metadata: dict[str, Any] | None = None) -> list[TextChunk]:
        base_meta = dict(metadata or {})
        tokens = text.split()
        if not tokens:
            return []

        step = self.chunk_size - self.chunk_overlap
        chunks: list[TextChunk] = []
        start = 0
        index = 0
        while start < len(tokens):
            end = min(start + self.chunk_size, len(tokens))
            piece = tokens[start:end]
            content = " ".join(piece)
            chunks.append(
                TextChunk(
                    content=content,
                    index=index,
                    token_count=len(piece),
                    metadata={**base_meta, "chunk_index": index},
                )
            )
            index += 1
            if end >= len(tokens):
                break
            start += step
        return chunks


def get_default_chunker(chunk_size: int | None = None, chunk_overlap: int | None = None) -> TokenChunker:
    from app.config import get_settings

    settings = get_settings()
    return TokenChunker(
        chunk_size=chunk_size if chunk_size is not None else settings.chunk_size_tokens,
        chunk_overlap=chunk_overlap if chunk_overlap is not None else settings.chunk_overlap_tokens,
    )
