"""Stub LLM providers (OpenAI / Anthropic / Gemini integration points)."""

from typing import Any

from app.modules.ai.domain.interfaces import LLMProvider


class EchoLLMProvider(LLMProvider):
    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return f"[echo-llm] {prompt}"
