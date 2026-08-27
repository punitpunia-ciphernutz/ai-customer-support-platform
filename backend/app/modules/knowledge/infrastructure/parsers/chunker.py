"""Token-oriented text chunking — LangChain splitter behind Chunker interface."""

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
    """LangChain RecursiveCharacterTextSplitter with token-sized windows.

    Uses whitespace token counts for size/overlap configuration (~500–800 tokens
    with ~50–100 overlap), implemented via LangChain as the document-processing layer.
    """

    def __init__(self, chunk_size: int = 600, chunk_overlap: int = 80) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size must be >= 1")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be >= 0")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be < chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def _splitter(self):  # type: ignore[no-untyped-def]
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        # Approximate tokens as whitespace-separated words via a custom length fn.
        return RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=lambda text: len(text.split()),
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def chunk(self, text: str, *, metadata: dict[str, Any] | None = None) -> list[TextChunk]:
        base_meta = dict(metadata or {})
        if not text.strip():
            return []
        pieces = self._splitter().split_text(text)
        chunks: list[TextChunk] = []
        for index, content in enumerate(pieces):
            token_count = len(content.split())
            chunks.append(
                TextChunk(
                    content=content,
                    index=index,
                    token_count=token_count,
                    metadata={**base_meta, "chunk_index": index},
                )
            )
        return chunks


def get_default_chunker(chunk_size: int | None = None, chunk_overlap: int | None = None) -> TokenChunker:
    from app.config import get_settings

    settings = get_settings()
    return TokenChunker(
        chunk_size=chunk_size if chunk_size is not None else settings.chunk_size_tokens,
        chunk_overlap=chunk_overlap if chunk_overlap is not None else settings.chunk_overlap_tokens,
    )
