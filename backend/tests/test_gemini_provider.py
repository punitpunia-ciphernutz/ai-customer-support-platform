"""Gemini LLM + embedding provider wiring (no live API calls)."""

from app.config import get_settings
from app.modules.ai.infrastructure.llm.providers import (
    DEFAULT_GEMINI_MODEL,
    EchoLLMProvider,
    GeminiLLMProvider,
    get_llm_provider,
)
from app.modules.knowledge.infrastructure.embeddings import (
    DEFAULT_GEMINI_EMBEDDING_MODEL,
    GeminiEmbeddingProvider,
    OfflineSemanticEmbeddingProvider,
    get_embedding_provider,
)


def test_default_gemini_model_id() -> None:
    assert DEFAULT_GEMINI_MODEL == "gemini-3.1-flash-lite"
    settings = get_settings()
    assert settings.llm_model == "gemini-3.1-flash-lite"
    assert settings.embedding_model == DEFAULT_GEMINI_EMBEDDING_MODEL


def test_get_llm_provider_falls_back_without_key() -> None:
    provider = get_llm_provider()
    assert isinstance(provider, EchoLLMProvider)


def test_get_embedding_provider_falls_back_without_key() -> None:
    provider = get_embedding_provider()
    assert isinstance(provider, OfflineSemanticEmbeddingProvider)


def test_gemini_provider_constructed_with_model() -> None:
    provider = GeminiLLMProvider(api_key="test-not-used", model=DEFAULT_GEMINI_MODEL)
    assert provider.model == "gemini-3.1-flash-lite"


def test_gemini_embedding_provider_constructed() -> None:
    provider = GeminiEmbeddingProvider(api_key="test-not-used", dimensions=1536)
    assert provider.model == DEFAULT_GEMINI_EMBEDDING_MODEL
    assert provider.dimensions == 1536
