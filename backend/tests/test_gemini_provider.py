"""Gemini LLM + embedding provider wiring (no live API calls)."""

import pytest

from app.config import get_settings
from app.modules.ai.infrastructure.llm.providers import (
    DEFAULT_GEMINI_MODEL,
    EchoLLMProvider,
    GeminiLLMProvider,
    available_llm_model_options,
    get_llm_provider,
    normalize_llm_model,
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


def test_get_llm_provider_falls_back_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()
    try:
        provider = get_llm_provider()
        assert isinstance(provider, EchoLLMProvider)
    finally:
        get_settings.cache_clear()


def test_get_llm_provider_respects_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-used")
    get_settings.cache_clear()
    try:
        provider = get_llm_provider(model="gemini-2.5-pro")
        assert isinstance(provider, GeminiLLMProvider)
        assert provider.model == "gemini-2.5-pro"
    finally:
        get_settings.cache_clear()


def test_normalize_llm_model_rejects_unknown() -> None:
    assert normalize_llm_model("gemini-2.5-flash") == "gemini-2.5-flash"
    assert normalize_llm_model("totally-fake-model") == DEFAULT_GEMINI_MODEL
    assert normalize_llm_model(None) == DEFAULT_GEMINI_MODEL


def test_available_llm_models_include_default() -> None:
    ids = {o["id"] for o in available_llm_model_options()}
    assert DEFAULT_GEMINI_MODEL in ids
    assert "gemini-2.5-pro" in ids


def test_get_embedding_provider_falls_back_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()
    try:
        provider = get_embedding_provider()
        assert isinstance(provider, OfflineSemanticEmbeddingProvider)
    finally:
        get_settings.cache_clear()


def test_gemini_provider_constructed_with_model() -> None:
    provider = GeminiLLMProvider(api_key="test-not-used", model=DEFAULT_GEMINI_MODEL)
    assert provider.model == "gemini-3.1-flash-lite"


def test_gemini_embedding_provider_constructed() -> None:
    provider = GeminiEmbeddingProvider(api_key="test-not-used", dimensions=1536)
    assert provider.model == DEFAULT_GEMINI_EMBEDDING_MODEL
    assert provider.dimensions == 1536
