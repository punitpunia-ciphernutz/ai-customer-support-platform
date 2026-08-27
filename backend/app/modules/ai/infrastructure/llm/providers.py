"""LLM provider abstraction — one OpenAI impl + echo/heuristic fallback."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from app.config import get_settings

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, **kwargs: Any) -> str:
        raise NotImplementedError

    @abstractmethod
    async def structured_output(self, prompt: str, schema: type[T], **kwargs: Any) -> T:
        raise NotImplementedError

    @abstractmethod
    async def stream(self, prompt: str, **kwargs: Any):  # type: ignore[no-untyped-def]
        raise NotImplementedError


class EchoLLMProvider(LLMProvider):
    """Deterministic classifier for offline / tests (keyword heuristics)."""

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        return f"[echo-llm] {prompt}"

    async def structured_output(self, prompt: str, schema: type[T], **kwargs: Any) -> T:
        from app.modules.ai.domain.schemas import AIClassification, IntentLabel

        if schema is AIClassification:
            lower = prompt.lower()
            intent = IntentLabel.OTHER
            requires_human = False
            if any(w in lower for w in ("login", "password", "account", "access", "sign in")):
                intent = IntentLabel.ACCOUNT_ACCESS
            elif any(w in lower for w in ("bill", "invoice", "charge", "payment")):
                intent = IntentLabel.BILLING
            elif any(w in lower for w in ("bug", "crash", "error", "broken")):
                intent = IntentLabel.BUG_REPORT
            elif any(w in lower for w in ("refund",)):
                intent = IntentLabel.REFUND
                requires_human = True
            elif any(w in lower for w in ("cancel",)):
                intent = IntentLabel.CANCELLATION
                requires_human = True
            elif any(w in lower for w in ("feature", "request")):
                intent = IntentLabel.FEATURE_REQUEST
            elif any(w in lower for w in ("how", "what", "where", "?")):
                intent = IntentLabel.GENERAL_QUESTION
            elif any(w in lower for w in ("not work", "issue", "problem", "technical")):
                intent = IntentLabel.TECHNICAL_ISSUE
            return schema.model_validate(
                {
                    "intent": intent,
                    "language": "en",
                    "sentiment": "frustrated" if "cannot" in lower or "can't" in lower else "neutral",
                    "confidence": 0.86,
                    "requires_human": requires_human,
                }
            )
        raise NotImplementedError(f"EchoLLMProvider has no heuristic for {schema}")

    async def stream(self, prompt: str, **kwargs: Any):
        yield await self.generate(prompt, **kwargs)


class OpenAILLMProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self.api_key = api_key
        self.model = model
        self._url = "https://api.openai.com/v1/chat/completions"

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        data = await self._chat([{"role": "user", "content": prompt}], response_format=None)
        return data["choices"][0]["message"]["content"]

    async def structured_output(self, prompt: str, schema: type[T], **kwargs: Any) -> T:
        system = (
            "You are a support intent classifier. "
            "Respond with JSON matching the provided schema only."
        )
        schema_hint = schema.model_json_schema()
        user = f"Schema:\n{json.dumps(schema_hint)}\n\nMessage to classify:\n{prompt}"
        data = await self._chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
        )
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return schema.model_validate(parsed)

    async def stream(self, prompt: str, **kwargs: Any):
        # Day 2: non-streaming fallback
        yield await self.generate(prompt, **kwargs)

    async def _chat(self, messages: list[dict[str, str]], response_format: dict | None) -> dict:
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": 0}
        if response_format:
            payload["response_format"] = response_format
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self._url,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            return response.json()


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.has_openai:
        return OpenAILLMProvider(api_key=settings.openai_api_key, model=settings.llm_model)
    return EchoLLMProvider()
