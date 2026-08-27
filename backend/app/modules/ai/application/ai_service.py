"""AIService boundary — ConversationService must not call LangGraph directly."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.modules.ai.domain.models import AIRun, AIRunStatus, AIRunType
from app.modules.ai.domain.schemas import AIClassification
from app.modules.ai.graphs.classification import timed_classification
from app.modules.ai.infrastructure.llm.providers import LLMProvider, get_llm_provider


class AIService:
    def __init__(self, db: AsyncSession, llm: LLMProvider | None = None) -> None:
        self.db = db
        self.llm = llm or get_llm_provider()
        self.settings = get_settings()

    async def classify(
        self,
        message: str,
        *,
        conversation_id: str | None = None,
        message_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> tuple[AIClassification, AIRun]:
        run = AIRun(
            conversation_id=conversation_id,
            message_id=message_id,
            type=AIRunType.CLASSIFICATION,
            status=AIRunStatus.RUNNING,
            model=self.settings.llm_model if self.settings.has_openai else "echo-heuristic",
            input={"message": message, "context": context or {}},
        )
        self.db.add(run)
        await self.db.flush()

        try:
            classification, latency_ms = await timed_classification(
                message, context=context, llm=self.llm
            )
            run.status = AIRunStatus.SUCCEEDED
            run.output = classification.model_dump(mode="json")
            run.latency_ms = latency_ms
            run.token_usage = {"approx": True}
            await self.db.flush()
            await self.db.refresh(run)
            return classification, run
        except Exception as exc:  # noqa: BLE001
            run.status = AIRunStatus.FAILED
            run.error = str(exc)[:2000]
            await self.db.flush()
            await self.db.refresh(run)
            raise

    async def generate(self, prompt: str) -> str:
        return await self.llm.generate(prompt)

    async def summarize(self, text: str) -> str:
        return await self.llm.generate(f"Summarize briefly:\n{text}")
