"""Embedding provider abstraction + deterministic hash implementation.

OpenAI embeddings removed — knowledge search uses local hash vectors until a
Gemini (or other) embedding provider is wired behind this same interface.
"""

from __future__ import annotations

import hashlib
import math
import struct
from abc import ABC, abstractmethod

from app.config import get_settings
from app.modules.knowledge.domain.models import EMBEDDING_DIMENSIONS


class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError


class HashEmbeddingProvider(EmbeddingProvider):
    """Deterministic local embeddings for tests / offline MVP (not semantic)."""

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self.dimensions = dimensions

    def _embed_one(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        seed = digest
        while len(values) < self.dimensions:
            seed = hashlib.sha256(seed).digest()
            for i in range(0, len(seed), 4):
                if len(values) >= self.dimensions:
                    break
                (n,) = struct.unpack_from("!I", seed, i)
                values.append((n / 0xFFFFFFFF) * 2.0 - 1.0)
        # L2-normalize for cosine-friendly similarity
        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)


def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    return HashEmbeddingProvider(dimensions=settings.embedding_dimensions)
