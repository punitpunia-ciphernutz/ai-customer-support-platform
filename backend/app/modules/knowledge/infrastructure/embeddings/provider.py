"""Embedding provider abstraction + OpenAI / deterministic hash implementations."""

from __future__ import annotations

import hashlib
import math
import struct
from abc import ABC, abstractmethod

import httpx

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


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI embeddings via HTTP (kept behind EmbeddingProvider; not called from routes)."""

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int = EMBEDDING_DIMENSIONS,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions
        self._url = "https://api.openai.com/v1/embeddings"

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await self._embed(texts)

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self._embed([text])
        return vectors[0]

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        payload: dict = {"model": self.model, "input": texts}
        if self.model.startswith("text-embedding-3"):
            payload["dimensions"] = self.dimensions
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self._url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()["data"]
            data_sorted = sorted(data, key=lambda row: row["index"])
            return [row["embedding"] for row in data_sorted]


def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.has_openai:
        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    return HashEmbeddingProvider(dimensions=settings.embedding_dimensions)
