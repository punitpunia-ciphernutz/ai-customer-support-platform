"""Embedding provider abstraction — Gemini semantic + offline lexical fallback.

OpenAI is not used. Production path: Gemini `gemini-embedding-001`.
Offline / tests without API key: bag-of-words hashing trick (token-overlap semantic).
"""

from __future__ import annotations

import hashlib
import math
import re
import struct
from abc import ABC, abstractmethod

from app.config import get_settings
from app.modules.knowledge.domain.models import EMBEDDING_DIMENSIONS

DEFAULT_GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"


class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError


def _l2_normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


class OfflineSemanticEmbeddingProvider(EmbeddingProvider):
    """Deterministic bag-of-words embeddings for offline demos and tests.

    Texts that share tokens score higher under cosine similarity (unlike pure
    SHA hashing of the full string). Not a substitute for Gemini in production.
    """

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self.dimensions = dimensions

    def _embed_one(self, text: str) -> list[float]:
        values = [0.0] * self.dimensions
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        if not tokens:
            values[0] = 1.0
            return _l2_normalize(values)
        for tok in tokens:
            digest = hashlib.sha256(tok.encode("utf-8")).digest()
            for i in range(0, len(digest), 4):
                (n,) = struct.unpack_from("!I", digest, i)
                idx = n % self.dimensions
                sign = 1.0 if (digest[i] % 2 == 0) else -1.0
                values[idx] += sign
        return _l2_normalize(values)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)


# Back-compat alias for older tests / imports
HashEmbeddingProvider = OfflineSemanticEmbeddingProvider


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Google Gemini embeddings via `google-genai` (`gemini-embedding-001`)."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_GEMINI_EMBEDDING_MODEL,
        dimensions: int = EMBEDDING_DIMENSIONS,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions

    def _client(self):  # type: ignore[no-untyped-def]
        from google import genai

        return genai.Client(api_key=self.api_key)

    async def _embed(self, texts: list[str], *, task_type: str) -> list[list[float]]:
        from google.genai import types

        if not texts:
            return []
        client = self._client()
        response = await client.aio.models.embed_content(
            model=self.model,
            contents=texts,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=self.dimensions,
            ),
        )
        embeddings = getattr(response, "embeddings", None) or []
        if len(embeddings) != len(texts):
            raise ValueError(
                f"Gemini returned {len(embeddings)} embeddings for {len(texts)} texts"
            )
        return [_l2_normalize(list(e.values)) for e in embeddings]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, task_type="RETRIEVAL_DOCUMENT")

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self._embed([text], task_type="RETRIEVAL_QUERY")
        return vectors[0]


def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.has_gemini:
        return GeminiEmbeddingProvider(
            api_key=settings.gemini_api_key,
            model=settings.embedding_model or DEFAULT_GEMINI_EMBEDDING_MODEL,
            dimensions=settings.embedding_dimensions,
        )
    return OfflineSemanticEmbeddingProvider(dimensions=settings.embedding_dimensions)
