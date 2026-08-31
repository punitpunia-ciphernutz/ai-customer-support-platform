"""LLM provider abstraction — Gemini impl + echo/heuristic fallback."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel

from app.config import get_settings

T = TypeVar("T", bound=BaseModel)

# Stable Gemini API model id (Google AI for Developers, May 2026).
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"


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
        from app.modules.ai.domain.schemas import AIClassification, GeneratedAnswer, IntentLabel
        from app.modules.ai.infrastructure.reranker import RelevanceScore

        if schema is AIClassification:
            lower = prompt.lower()
            intent = IntentLabel.OTHER
            requires_human = False
            language = "es" if any(w in lower for w in ("cómo", "contraseña", "restablecer")) else "en"
            if any(w in lower for w in ("human", "representative", "real person", "speak to")):
                intent = IntentLabel.OTHER
                requires_human = True
            elif any(w in lower for w in ("login", "password", "account", "access", "sign in", "contraseña")):
                intent = IntentLabel.ACCOUNT_ACCESS
            elif any(w in lower for w in ("bill", "invoice", "charge", "payment", "billing plan")):
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
            elif any(w in lower for w in ("not work", "isn't working", "issue", "problem", "technical")):
                intent = IntentLabel.TECHNICAL_ISSUE
            elif "integrat" in lower and "xyz" in lower:
                intent = IntentLabel.GENERAL_QUESTION
            return schema.model_validate(
                {
                    "intent": intent,
                    "language": language,
                    "sentiment": "frustrated" if "cannot" in lower or "can't" in lower else "neutral",
                    "confidence": 0.94 if intent != IntentLabel.OTHER else 0.72,
                    "requires_human": requires_human,
                }
            )

        if schema is GeneratedAnswer:
            lower = prompt.lower()
            if any(w in lower for w in ("human", "representative", "real person")):
                return schema.model_validate(
                    {
                        "answer": "I'll connect you with a human agent who can help.",
                        "grounded": False,
                        "needs_clarification": False,
                    }
                )
            if "isn't working" in lower or "it isn't working" in lower:
                return schema.model_validate(
                    {
                        "answer": "I'm sorry you're having trouble. Could you share more details about what isn't working?",
                        "grounded": False,
                        "needs_clarification": True,
                    }
                )
            if "billing plan" in lower or "change my billing" in lower:
                return schema.model_validate(
                    {
                        "answer": "I don't have enough information to change billing plans on your behalf.",
                        "grounded": False,
                        "needs_clarification": False,
                    }
                )
            if "integrat" in lower and "xyz" in lower:
                return schema.model_validate(
                    {
                        "answer": "I don't have documentation about an XYZ integration in our knowledge base.",
                        "grounded": False,
                        "needs_clarification": False,
                    }
                )
            if any(w in lower for w in ("password", "reset", "contraseña", "restablecer")):
                answer = (
                    "Puede restablecer su contraseña desde Configuración → Seguridad → Restablecer contraseña."
                    if "contraseña" in lower or "restablecer" in lower
                    else "You can reset your password from Settings → Security → Reset Password."
                )
                return schema.model_validate(
                    {"answer": answer, "grounded": True, "needs_clarification": False}
                )
            return schema.model_validate(
                {
                    "answer": "I don't have enough information in our knowledge base to answer that confidently.",
                    "grounded": False,
                    "needs_clarification": True,
                }
            )

        if schema is RelevanceScore:
            lower = prompt.lower()
            score = 0.25
            if "password" in lower and ("reset" in lower or "forgot" in lower):
                score = 0.95
            elif "billing" in lower or "plan" in lower:
                score = 0.2
            elif "xyz" in lower:
                score = 0.1
            return schema.model_validate({"relevance": score})

        raise NotImplementedError(f"EchoLLMProvider has no heuristic for {schema}")

    async def stream(self, prompt: str, **kwargs: Any):
        yield await self.generate(prompt, **kwargs)


class GeminiLLMProvider(LLMProvider):
    """Google Gemini via the official `google-genai` SDK."""

    def __init__(self, api_key: str, model: str = DEFAULT_GEMINI_MODEL) -> None:
        self.api_key = api_key
        self.model = model

    def _client(self):  # type: ignore[no-untyped-def]
        from google import genai

        return genai.Client(api_key=self.api_key)

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        client = self._client()
        response = await client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        text = getattr(response, "text", None) or ""
        if not text and getattr(response, "candidates", None):
            # Fallback if .text helper is empty
            parts = response.candidates[0].content.parts
            text = "".join(getattr(p, "text", "") or "" for p in parts)
        return text

    async def structured_output(self, prompt: str, schema: type[T], **kwargs: Any) -> T:
        from google.genai import types

        system = (
            "You are a support intent classifier. "
            "Respond with JSON matching the provided schema only."
        )
        client = self._client()
        response = await client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0,
                response_mime_type="application/json",
                response_json_schema=schema.model_json_schema(),
            ),
        )
        text = getattr(response, "text", None) or ""
        if not text:
            raise ValueError("Gemini returned empty structured output")
        return schema.model_validate(json.loads(text))

    async def stream(self, prompt: str, **kwargs: Any):
        # Day 2: non-streaming fallback
        yield await self.generate(prompt, **kwargs)


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.has_gemini:
        return GeminiLLMProvider(api_key=settings.gemini_api_key, model=settings.llm_model)
    return EchoLLMProvider()
