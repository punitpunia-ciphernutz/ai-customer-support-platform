"""AIService boundary — ConversationService must not call LangGraph directly."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.infrastructure.database.models import Message, SenderType
from app.modules.ai.application.ai_config_service import get_or_create_ai_config
from app.modules.ai.application.context_builder import ContextBuilder
from app.modules.ai.application.escalation_service import EscalationService
from app.modules.ai.domain.models import AIRun, AIRunStatus, AIRunType
from app.modules.ai.domain.schemas import (
    AIClassification,
    AIResponse,
    AgentDecision,
    IntentLabel,
    SupportAgentState,
)
from app.modules.ai.graphs.classification import timed_classification
from app.modules.ai.graphs.support_agent import GRAPH_VERSION, timed_support_agent
from app.modules.ai.infrastructure.llm.providers import LLMProvider, get_llm_provider
from app.modules.conversations.service import ConversationService


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
            model=self.settings.llm_model if self.settings.has_gemini else "echo-heuristic",
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
            run.intent = classification.intent.value
            run.confidence = classification.confidence
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

    async def run_support_agent(
        self,
        conversation_id: str,
        message_id: str,
        *,
        persist_side_effects: bool = True,
    ) -> tuple[AIResponse, AIRun]:
        conversations = ConversationService(self.db)
        conv = await conversations.get_conversation_by_id(conversation_id)
        config = await get_or_create_ai_config(self.db, conv.organization_id)

        if not config.enabled:
            raise ValueError("AI is disabled for this organization")

        run, skip_processing = await self._acquire_agent_run(conversation_id, message_id)
        if skip_processing:
            response = self._response_from_run(run)
            if response is not None:
                return response, run
            return self._empty_response(run), run

        run.status = AIRunStatus.RUNNING
        await self.db.flush()

        try:
            state = await ContextBuilder(self.db).build(conversation_id, message_id)
            final_state, latency_ms = await timed_support_agent(
                state, config=config, llm=self.llm, db_session=self.db
            )
            run.status = AIRunStatus.COMPLETED
            run.intent = final_state.intent.value if final_state.intent else None
            run.retrieval_count = len(final_state.retrieved_documents)
            run.confidence = final_state.support_confidence
            run.latency_ms = latency_ms
            run.token_usage = {"approx": True}
            run.output = final_state.model_dump(mode="json")
            run.error = None

            response = AIResponse(
                answer=final_state.final_response or final_state.draft_response or "",
                intent=final_state.intent or IntentLabel.OTHER,
                confidence=final_state.support_confidence,
                grounded=final_state.grounded,
                escalation_required=final_state.escalation_required,
                escalation_reason=final_state.escalation_reason,
                citations=final_state.citations,
                decision=final_state.decision or AgentDecision.ESCALATE,
                ai_run_id=run.id,
            )

            if persist_side_effects:
                await self._apply_side_effects(final_state, response, run, config)

            await self.db.flush()
            await self.db.refresh(run)
            return response, run
        except Exception as exc:  # noqa: BLE001
            run.status = AIRunStatus.FAILED
            run.error = str(exc)[:2000]
            await self.db.flush()
            await self.db.refresh(run)
            raise

    async def run_test(
        self,
        message: str,
        *,
        organization_id: str,
        conversation_id: str | None = None,
    ) -> AIResponse:
        config = await get_or_create_ai_config(self.db, organization_id)
        state = SupportAgentState(
            organization_id=organization_id,
            conversation_id=conversation_id,
            user_message=message,
        )
        if conversation_id:
            state = await ContextBuilder(self.db).build(conversation_id)
            state.user_message = message

        final_state, _latency = await timed_support_agent(
            state, config=config, llm=self.llm, db_session=self.db
        )
        return AIResponse(
            answer=final_state.final_response or final_state.draft_response or "",
            intent=final_state.intent or IntentLabel.OTHER,
            confidence=final_state.support_confidence,
            grounded=final_state.grounded,
            escalation_required=final_state.escalation_required,
            escalation_reason=final_state.escalation_reason,
            citations=final_state.citations,
            decision=final_state.decision or AgentDecision.ESCALATE,
        )

    async def process_customer_message(self, message_id: str) -> AIRun | None:
        msg = await self.db.get(Message, message_id)
        if msg is None or msg.sender_type != SenderType.CUSTOMER:
            return None

        existing = await self._get_existing_agent_run(message_id)
        if existing is not None and existing.status in {
            AIRunStatus.PENDING,
            AIRunStatus.RUNNING,
            AIRunStatus.COMPLETED,
            AIRunStatus.SUCCEEDED,
        }:
            return existing

        _, run = await self.run_support_agent(msg.conversation_id, message_id, persist_side_effects=True)
        return run

    async def _apply_side_effects(
        self,
        state: SupportAgentState,
        response: AIResponse,
        run: AIRun,
        config: Any,
    ) -> None:
        from app.modules.ai.domain.models import AIMode

        if config.mode == AIMode.DRAFT_ONLY:
            return

        if response.decision == AgentDecision.AI_RESOLVE and config.mode == AIMode.AUTO_REPLY:
            await self._save_ai_reply(state, response, run)
        elif response.decision == AgentDecision.ESCALATE and config.mode in {AIMode.AUTO_REPLY, AIMode.SUGGEST}:
            await EscalationService(self.db).create_from_ai_run(
                state,
                organization_id=state.organization_id or "",
                ai_run_id=run.id,
                intent_team_map=config.intent_team_map,
            )

    async def _save_ai_reply(self, state: SupportAgentState, response: AIResponse, run: AIRun) -> Message | None:
        if state.message_id and await self._ai_reply_exists(state.message_id):
            return None

        conversations = ConversationService(self.db)
        conv = await conversations.get_conversation_by_id(state.conversation_id or "")
        msg = Message(
            conversation_id=state.conversation_id,
            sender_type=SenderType.AI,
            sender_id=None,
            content=response.answer,
            metadata_={
                "ai_run_id": run.id,
                "trigger_message_id": state.message_id,
                "confidence": response.confidence,
                "intent": response.intent.value,
                "grounded": response.grounded,
                "citations": [c.model_dump() for c in response.citations],
                "ai_status": "AI Resolved",
            },
        )
        self.db.add(msg)
        await self.db.flush()
        await conversations._publish_message(msg, conv)  # noqa: SLF001
        return msg

    async def _acquire_agent_run(
        self,
        conversation_id: str,
        message_id: str,
    ) -> tuple[AIRun, bool]:
        """Return an agent run and whether graph execution should be skipped."""
        existing = await self._get_existing_agent_run(message_id)
        if existing is not None:
            if existing.status in {
                AIRunStatus.COMPLETED,
                AIRunStatus.SUCCEEDED,
                AIRunStatus.RUNNING,
                AIRunStatus.PENDING,
            }:
                return existing, True
            if existing.status == AIRunStatus.FAILED:
                existing.status = AIRunStatus.PENDING
                existing.error = None
                existing.output = None
                existing.intent = None
                existing.retrieval_count = None
                existing.confidence = None
                existing.latency_ms = None
                existing.token_usage = None
                await self.db.flush()
                return existing, False

        processing_key = f"{conversation_id}:{message_id}"
        run = AIRun(
            conversation_id=conversation_id,
            message_id=message_id,
            type=AIRunType.AGENT,
            status=AIRunStatus.PENDING,
            model=self.settings.llm_model if self.settings.has_gemini else "echo-heuristic",
            graph_version=GRAPH_VERSION,
            processing_key=processing_key,
            input={"conversation_id": conversation_id, "message_id": message_id},
        )
        self.db.add(run)
        try:
            await self.db.flush()
        except IntegrityError:
            # Concurrent Celery workers can race on the same customer message.
            await self.db.rollback()
            existing = await self._get_existing_agent_run(message_id)
            if existing is None:
                raise
            if existing.status == AIRunStatus.FAILED:
                existing.status = AIRunStatus.PENDING
                existing.error = None
                existing.output = None
                existing.intent = None
                existing.retrieval_count = None
                existing.confidence = None
                existing.latency_ms = None
                existing.token_usage = None
                await self.db.flush()
                return existing, False
            return existing, True
        return run, False

    async def _ai_reply_exists(self, trigger_message_id: str) -> bool:
        result = await self.db.execute(
            select(Message.id).where(
                Message.sender_type == SenderType.AI,
                Message.metadata_["trigger_message_id"].astext == trigger_message_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def _get_existing_agent_run(self, message_id: str) -> AIRun | None:
        result = await self.db.execute(
            select(AIRun)
            .where(
                AIRun.message_id == message_id,
                AIRun.type == AIRunType.AGENT,
            )
            .order_by(AIRun.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    def _empty_response(self, run: AIRun) -> AIResponse:
        return AIResponse(
            answer="",
            intent=IntentLabel.OTHER,
            confidence=run.confidence or 0.0,
            grounded=False,
            escalation_required=True,
            escalation_reason="AI agent run in progress or pending",
            citations=[],
            decision=AgentDecision.ESCALATE,
            ai_run_id=run.id,
        )

    def _response_from_run(self, run: AIRun) -> AIResponse | None:
        if not run.output:
            return None
        state = SupportAgentState.model_validate(run.output)
        return AIResponse(
            answer=state.final_response or state.draft_response or "",
            intent=state.intent or IntentLabel.OTHER,
            confidence=state.support_confidence,
            grounded=state.grounded,
            escalation_required=state.escalation_required,
            escalation_reason=state.escalation_reason,
            citations=state.citations,
            decision=state.decision or AgentDecision.ESCALATE,
            ai_run_id=run.id,
        )

    async def generate(self, prompt: str) -> str:
        return await self.llm.generate(prompt)

    async def summarize(self, text: str) -> str:
        return await self.llm.generate(f"Summarize briefly:\n{text}")
