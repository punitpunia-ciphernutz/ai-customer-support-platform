"""Gemini LLM provider wiring (no live API calls)."""

from app.config import get_settings
from app.modules.ai.infrastructure.llm.providers import (
    DEFAULT_GEMINI_MODEL,
    EchoLLMProvider,
    GeminiLLMProvider,
    get_llm_provider,
)


def test_default_gemini_model_id() -> None:
    assert DEFAULT_GEMINI_MODEL == "gemini-3.1-flash-lite"
    settings = get_settings()
    assert settings.llm_model == "gemini-3.1-flash-lite"


def test_get_llm_provider_falls_back_without_key() -> None:
    provider = get_llm_provider()
    assert isinstance(provider, EchoLLMProvider)


def test_gemini_provider_constructed_with_model() -> None:
    provider = GeminiLLMProvider(api_key="test-not-used", model=DEFAULT_GEMINI_MODEL)
    assert provider.model == "gemini-3.1-flash-lite"
