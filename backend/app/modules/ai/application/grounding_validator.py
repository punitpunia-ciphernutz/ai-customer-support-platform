"""Post-generation grounding validation — separate from generation model self-report."""

from __future__ import annotations

from app.modules.ai.domain.schemas import Citation, GroundingResult, RetrievedDocument
from app.modules.ai.infrastructure.llm.providers import LLMProvider, get_llm_provider


class GroundingValidator:
    def __init__(self, llm: LLMProvider | None = None) -> None:
        self.llm = llm or get_llm_provider()

    async def validate(
        self,
        answer: str,
        sources: list[RetrievedDocument] | list[Citation],
        *,
        source_contents: list[RetrievedDocument] | None = None,
    ) -> GroundingResult:
        if not answer.strip():
            return GroundingResult(grounded=False, score=0.0, unsupported_claims=["Empty answer"])

        docs = source_contents or []
        if not docs and not sources:
            return GroundingResult(
                grounded=False,
                score=0.0,
                unsupported_claims=["No knowledge sources provided"],
            )

        knowledge_text = ""
        if docs:
            knowledge_text = "\n\n".join(f"### {d.title}\n{d.content[:800]}" for d in docs)
        else:
            knowledge_text = "\n".join(
                f"- {s.title}" for s in sources if hasattr(s, "title")
            )

        prompt = (
            "You are a grounding validator. Given retrieved knowledge and a generated answer, "
            "determine if the answer is supported by the knowledge.\n\n"
            f"KNOWLEDGE:\n{knowledge_text or '(none)'}\n\n"
            f"ANSWER:\n{answer}\n\n"
            'Respond with JSON: {"grounded": <bool>, "score": <0.0-1.0>, "unsupported_claims": [<string>]}'
        )

        try:
            result = await self.llm.structured_output(prompt, GroundingResult)
            return result
        except Exception:  # noqa: BLE001
            # Heuristic fallback
            if not docs:
                return GroundingResult(grounded=False, score=0.2)
            grounded = bool(docs) and len(answer) > 10
            return GroundingResult(grounded=grounded, score=0.85 if grounded else 0.3)

    async def validate_with_prompt(
        self,
        prompt: str,
        answer: str,
        sources: list[RetrievedDocument] | list[Citation],
        *,
        source_contents: list[RetrievedDocument] | None = None,
    ) -> GroundingResult:
        if not answer.strip():
            return GroundingResult(grounded=False, score=0.0, unsupported_claims=["Empty answer"])
        docs = source_contents or []
        if not docs and not sources:
            return GroundingResult(
                grounded=False,
                score=0.0,
                unsupported_claims=["No knowledge sources provided"],
            )
        try:
            return await self.llm.structured_output(prompt, GroundingResult)
        except Exception:  # noqa: BLE001
            return await self.validate(answer, sources, source_contents=source_contents)
