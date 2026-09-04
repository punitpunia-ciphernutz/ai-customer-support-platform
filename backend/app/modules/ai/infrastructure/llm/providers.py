"""LLM provider abstraction — Gemini impl + echo/heuristic fallback."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel

from app.config import get_settings

T = TypeVar("T", bound=BaseModel)

DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"

# Models selectable from AI Support settings (Gemini).
AVAILABLE_LLM_MODELS: tuple[tuple[str, str], ...] = (
    ("gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite — fast, low cost"),
    ("gemini-2.5-flash", "Gemini 2.5 Flash — balanced"),
    ("gemini-2.5-pro", "Gemini 2.5 Pro — highest quality"),
)

AVAILABLE_LLM_MODEL_IDS: frozenset[str] = frozenset(m[0] for m in AVAILABLE_LLM_MODELS)


def available_llm_model_options() -> list[dict[str, str]]:
    return [{"id": model_id, "label": label} for model_id, label in AVAILABLE_LLM_MODELS]


def _echo_sentiment(lower: str) -> str:
    """Heuristic stand-in for LLM sentiment (Echo only). Uses intensity/meaning cues."""
    from app.modules.ai.domain.models import SentimentLabel

    angry_cues = (
        "third time",
        "furious",
        "terrible",
        "awful",
        "unacceptable",
        "!!!",
        "angry",
        "pissed",
        "rage",
        "hostile",
        "ridiculous",
        "worst",
        "useless",
        "fix your",
        "i'm done",
        "im done",
        "sick of",
        "hate this",
        "hate your",
        "sue you",
        "lawyer",
        "report you",
        "get angry",
        "makes me mad",
        "i am mad",
        "i'm mad",
    )
    negative_cues = (
        "cannot",
        "can't",
        "isn't working",
        "not work",
        "doesn't work",
        "does not work",
        "disappointed",
        "unhappy",
        "not happy",
        "frustrated",
        "upset",
        "too much",
        "annoyed",
        "problem",
        "issue",
    )
    positive_cues = (
        "thanks",
        "thank you",
        "thx",
        "great",
        "awesome",
        "perfect",
        "appreciate",
        "helpful",
        "love it",
    )
    if any(c in lower for c in angry_cues):
        return SentimentLabel.ANGRY.value
    if any(c in lower for c in negative_cues):
        return SentimentLabel.NEGATIVE.value
    if any(c in lower for c in positive_cues):
        return SentimentLabel.POSITIVE.value
    return SentimentLabel.NEUTRAL.value


def normalize_llm_model(model: str | None) -> str:
    """Return a supported model id, falling back to the env/default model."""
    settings = get_settings()
    candidate = (model or "").strip() or settings.llm_model or DEFAULT_GEMINI_MODEL
    if candidate in AVAILABLE_LLM_MODEL_IDS:
        return candidate
    # Allow the configured env model even if not in the curated UI list.
    if candidate == settings.llm_model:
        return candidate
    return DEFAULT_GEMINI_MODEL


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, other: TokenUsage) -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class LLMProvider(ABC):
    usage: TokenUsage = field(default_factory=TokenUsage)

    def reset_usage(self) -> None:
        self.usage = TokenUsage()

    @abstractmethod
    async def generate(self, prompt: str, **kwargs: Any) -> str:
        raise NotImplementedError

    @abstractmethod
    async def structured_output(self, prompt: str, schema: type[T], **kwargs: Any) -> T:
        raise NotImplementedError

    @abstractmethod
    async def stream(self, prompt: str, **kwargs: Any):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def _estimate_usage(self, prompt: str, output: str) -> TokenUsage:
        # Rough heuristic when provider metadata is unavailable (~4 chars/token).
        input_tokens = max(1, len(prompt) // 4)
        output_tokens = max(1, len(output) // 4) if output else 0
        return TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens)

    def _record_usage(self, prompt: str, output: str, metadata: TokenUsage | None = None) -> None:
        self.usage.add(metadata or self._estimate_usage(prompt, output))


class EchoLLMProvider(LLMProvider):
    """Deterministic classifier for offline / tests (keyword heuristics)."""

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        text = f"[echo-llm] {prompt[:500]}"
        self._record_usage(prompt, text)
        return text

    async def structured_output(self, prompt: str, schema: type[T], **kwargs: Any) -> T:
        from app.modules.ai.domain.schemas import AIClassification, GeneratedAnswer, IntentLabel
        from app.modules.ai.infrastructure.reranker import RelevanceScore

        lower = prompt.lower()
        result: BaseModel

        if schema is AIClassification:
            from app.modules.ai.domain.schemas import MessageKind

            intent = IntentLabel.OTHER
            requires_human = False
            language = "es" if any(w in lower for w in ("cómo", "contraseña", "restablecer")) else "en"
            sentiment = _echo_sentiment(lower)
            message_kind = MessageKind.SUPPORT_REQUEST
            message_kind_confidence = 0.9
            if any(w in lower for w in ("human", "representative", "real person", "speak to")):
                intent = IntentLabel.OTHER
                requires_human = True
                message_kind = MessageKind.HUMAN_REQUEST
            elif any(
                w in lower
                for w in ("who are you", "what are you", "are you a bot", "are you ai", "are you an ai")
            ):
                intent = IntentLabel.GENERAL_QUESTION
                message_kind = MessageKind.IDENTITY
            elif any(w in lower for w in ("login", "password", "account", "access", "sign in", "contraseña")):
                intent = IntentLabel.ACCOUNT_ACCESS
                message_kind = MessageKind.SUPPORT_REQUEST
            elif any(w in lower for w in ("bill", "invoice", "charge", "payment", "billing plan")):
                intent = IntentLabel.BILLING
                message_kind = MessageKind.SUPPORT_REQUEST
            elif any(w in lower for w in ("bug", "crash", "error", "broken")):
                intent = IntentLabel.BUG_REPORT
                message_kind = MessageKind.SUPPORT_REQUEST
            elif any(w in lower for w in ("refund",)):
                intent = IntentLabel.REFUND
                requires_human = True
                message_kind = MessageKind.SUPPORT_REQUEST
            elif any(w in lower for w in ("cancel",)):
                intent = IntentLabel.CANCELLATION
                requires_human = True
                message_kind = MessageKind.SUPPORT_REQUEST
            elif any(w in lower for w in ("feature", "request")):
                intent = IntentLabel.FEATURE_REQUEST
                message_kind = MessageKind.SUPPORT_REQUEST
            elif "integrat" in lower and "xyz" in lower:
                intent = IntentLabel.GENERAL_QUESTION
                message_kind = MessageKind.OUT_OF_DOMAIN
            elif any(w in lower for w in ("quantum", "physics", "joke", "weather")):
                intent = IntentLabel.GENERAL_QUESTION
                message_kind = MessageKind.OUT_OF_DOMAIN
            elif any(w in lower for w in ("asdfghjkl", "gibberish", "random")):
                intent = IntentLabel.OTHER
                message_kind = MessageKind.UNCLEAR
                message_kind_confidence = 0.7
            elif lower.strip() in {"help", "help?", "???", "?"}:
                intent = IntentLabel.GENERAL_QUESTION
                message_kind = MessageKind.UNCLEAR
                message_kind_confidence = 0.75
            elif any(w in lower for w in ("thanks", "thank you", "thx", "cool", "ok", "okay")):
                intent = IntentLabel.GENERAL_QUESTION
                message_kind = MessageKind.SMALL_TALK
            elif any(w in lower for w in ("how", "what", "where", "?")):
                intent = IntentLabel.GENERAL_QUESTION
                message_kind = MessageKind.SUPPORT_REQUEST
            elif any(w in lower for w in ("not work", "isn't working", "issue", "problem", "technical")):
                intent = IntentLabel.TECHNICAL_ISSUE
                message_kind = MessageKind.SUPPORT_REQUEST
            else:
                # Short hello-like prompts without a task
                stripped = lower.strip().strip("!.")
                if stripped in {"hello", "hi", "hey", "good morning", "good afternoon", "good evening"} or (
                    len(stripped.split()) <= 3 and any(g in stripped for g in ("hello", "hi", "hey"))
                ):
                    intent = IntentLabel.GENERAL_QUESTION
                    message_kind = MessageKind.GREETING
                elif intent == IntentLabel.OTHER:
                    message_kind = MessageKind.UNCLEAR
                    message_kind_confidence = 0.6
            result = schema.model_validate(
                {
                    "intent": intent,
                    "language": language,
                    "sentiment": sentiment,
                    "confidence": 0.94 if intent != IntentLabel.OTHER else 0.72,
                    "requires_human": requires_human,
                    "message_kind": message_kind,
                    "message_kind_confidence": message_kind_confidence,
                }
            )

        elif schema is GeneratedAnswer:
            if any(w in lower for w in ("human", "representative", "real person")):
                result = schema.model_validate(
                    {
                        "answer": "I'll connect you with a human agent who can help.",
                        "grounded": False,
                        "needs_clarification": False,
                    }
                )
            elif "isn't working" in lower or "it isn't working" in lower:
                result = schema.model_validate(
                    {
                        "answer": "I'm sorry you're having trouble. Could you share more details about what isn't working?",
                        "grounded": False,
                        "needs_clarification": True,
                    }
                )
            elif "billing plan" in lower or "change my billing" in lower:
                result = schema.model_validate(
                    {
                        "answer": "I don't have enough information to change billing plans on your behalf.",
                        "grounded": False,
                        "needs_clarification": False,
                    }
                )
            elif "integrat" in lower and "xyz" in lower:
                result = schema.model_validate(
                    {
                        "answer": "I don't have documentation about an XYZ integration in our knowledge base.",
                        "grounded": False,
                        "needs_clarification": False,
                    }
                )
            elif any(w in lower for w in ("password", "reset", "contraseña", "restablecer")):
                answer = (
                    "Puede restablecer su contraseña desde Configuración → Seguridad → Restablecer contraseña."
                    if "contraseña" in lower or "restablecer" in lower
                    else "You can reset your password from Settings → Security → Reset Password."
                )
                result = schema.model_validate(
                    {"answer": answer, "grounded": True, "needs_clarification": False}
                )
            else:
                result = schema.model_validate(
                    {
                        "answer": "I don't have enough information in our knowledge base to answer that confidently.",
                        "grounded": False,
                        "needs_clarification": True,
                    }
                )

        elif schema is RelevanceScore:
            score = 0.25
            if "password" in lower and ("reset" in lower or "forgot" in lower):
                score = 0.95
            elif "billing" in lower or "plan" in lower:
                score = 0.2
            elif "xyz" in lower:
                score = 0.1
            result = schema.model_validate({"relevance": score})

        else:
            from app.modules.ai.domain.schemas import GroundingResult

            if schema is GroundingResult:
                if "no knowledge" in lower or "(none)" in lower:
                    result = schema.model_validate(
                        {"grounded": False, "score": 0.15, "unsupported_claims": ["no sources"]}
                    )
                elif "password" in lower and "reset" in lower:
                    result = schema.model_validate(
                        {"grounded": True, "score": 0.94, "unsupported_claims": []}
                    )
                else:
                    result = schema.model_validate(
                        {"grounded": False, "score": 0.35, "unsupported_claims": ["unverified"]}
                    )
            else:
                raise NotImplementedError(f"EchoLLMProvider has no heuristic for {schema}")

        output = result.model_dump_json()
        self._record_usage(prompt, output)
        return result  # type: ignore[return-value]

    async def stream(self, prompt: str, **kwargs: Any):
        yield await self.generate(prompt, **kwargs)


class GeminiLLMProvider(LLMProvider):
    """Google Gemini via the official `google-genai` SDK."""

    def __init__(self, api_key: str, model: str = DEFAULT_GEMINI_MODEL) -> None:
        super().__init__()
        self.api_key = api_key
        self.model = model

    def _client(self):  # type: ignore[no-untyped-def]
        from google import genai

        return genai.Client(api_key=self.api_key)

    def _usage_from_response(self, response: Any, prompt: str, output: str) -> TokenUsage:
        meta = getattr(response, "usage_metadata", None)
        if meta is not None:
            prompt_tokens = int(getattr(meta, "prompt_token_count", 0) or 0)
            output_tokens = int(getattr(meta, "candidates_token_count", 0) or 0)
            if prompt_tokens or output_tokens:
                return TokenUsage(input_tokens=prompt_tokens, output_tokens=output_tokens)
        return self._estimate_usage(prompt, output)

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        client = self._client()
        response = await client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        text = getattr(response, "text", None) or ""
        if not text and getattr(response, "candidates", None):
            parts = response.candidates[0].content.parts
            text = "".join(getattr(p, "text", "") or "" for p in parts)
        self._record_usage(prompt, text, self._usage_from_response(response, prompt, text))
        return text

    async def structured_output(self, prompt: str, schema: type[T], **kwargs: Any) -> T:
        from google.genai import types

        from app.modules.ai.domain.schemas import AIClassification

        if schema is AIClassification:
            system = (
                "You are a support message understanding classifier. "
                "Return JSON matching the schema only. "
                "Set intent to the support topic (billing, account access, etc.). "
                "Set message_kind to the conversational act: "
                "GREETING (hello/hi with no task), IDENTITY (who/what are you), "
                "SMALL_TALK (thanks/ok without a task), "
                "SUPPORT_REQUEST (real help need — even if the message starts with hi), "
                "HUMAN_REQUEST (ask for a live agent), "
                "OUT_OF_DOMAIN (clearly outside product support), "
                "UNCLEAR (too vague to act). "
                "Prefer SUPPORT_REQUEST when a real task is present. "
                "Prefer HUMAN_REQUEST when the customer asks for a human. "
                "Missing knowledge is decided later — do not use OUT_OF_DOMAIN merely because "
                "you are unsure whether docs exist. "
                "message_kind_confidence is 0-1 for the kind label. "
                "Set sentiment from overall meaning, context, and emotional intensity — "
                "not from specific keywords alone. Use only: "
                "POSITIVE (thanks, praise, satisfaction), "
                "NEUTRAL (factual or no strong emotion), "
                "NEGATIVE (dissatisfaction or mild frustration without hostility; "
                "e.g. 'this isn't working', 'I'm disappointed'), "
                "ANGRY (strong anger, hostility, aggression, or threats — even without "
                "words like angry/mad; e.g. 'this is ridiculous, fix your mess', "
                "'I'm done with this service', 'now I get angry'). "
                "Prefer ANGRY over NEGATIVE when intensity is high or the tone is hostile."
            )
        else:
            system = (
                "You are a support assistant. "
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
        self._record_usage(prompt, text, self._usage_from_response(response, prompt, text))
        return schema.model_validate(json.loads(text))

    async def stream(self, prompt: str, **kwargs: Any):
        yield await self.generate(prompt, **kwargs)


def get_llm_provider(model: str | None = None) -> LLMProvider:
    settings = get_settings()
    if settings.has_gemini:
        return GeminiLLMProvider(
            api_key=settings.gemini_api_key,
            model=normalize_llm_model(model),
        )
    return EchoLLMProvider()
