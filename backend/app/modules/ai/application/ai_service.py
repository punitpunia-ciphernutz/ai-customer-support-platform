"""AIService boundary — ConversationService must not call LangGraph directly."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.infrastructure.database.models import Conversation, Message, SenderType
from app.modules.ai.application.ai_config_service import get_or_create_ai_config
from app.modules.ai.application.context_builder import ContextBuilder
from app.modules.ai.application.escalation_service import EscalationService
from app.modules.ai.application.runtime_config import RuntimeAIConfig
from app.modules.ai.domain.models import AIRun, AIRunStatus, AIRunType, AIMode
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
        self.llm.reset_usage()
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
            run.token_usage = self.llm.usage.to_dict()
            from app.modules.ai.application.cost_estimator import estimate_cost_usd

            run.estimated_cost_usd = estimate_cost_usd(run.model, run.token_usage)
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
        force: bool = False,
    ) -> tuple[AIResponse, AIRun]:
        conversations = ConversationService(self.db)
        conv = await conversations.get_conversation_by_id(conversation_id)
        config = await RuntimeAIConfig.resolve(self.db, conv.organization_id, conv.channel)

        if not config.enabled:
            raise ValueError("AI is disabled for this organization")

        run, skip_processing = await self._acquire_agent_run(conversation_id, message_id, force=force)
        if skip_processing:
            response = self._response_from_run(run)
            if response is not None:
                return response, run
            return self._empty_response(run), run

        run.status = AIRunStatus.RUNNING
        await self.db.flush()

        try:
            state = await ContextBuilder(self.db).build(conversation_id, message_id)
            final_state, latency_ms, token_usage = await timed_support_agent(
                state, config=config, llm=self.llm, db_session=self.db
            )
            run.status = AIRunStatus.COMPLETED
            run.intent = final_state.intent.value if final_state.intent else None
            run.retrieval_count = len(final_state.retrieved_documents)
            run.retrieval_score = final_state.retrieval_score
            run.grounding_score = final_state.grounding_score
            run.confidence = final_state.support_confidence
            run.confidence_components = (
                final_state.confidence_breakdown.model_dump(mode="json")
                if final_state.confidence_breakdown
                else None
            )
            run.decision = final_state.decision.value if final_state.decision else None
            run.language = final_state.language
            run.sentiment = final_state.sentiment
            run.prompt_version = final_state.prompt_version or GRAPH_VERSION
            run.trace = [s.model_dump() for s in final_state.trace_steps] if final_state.trace_steps else None
            run.latency_ms = latency_ms
            run.token_usage = token_usage
            from app.modules.ai.application.cost_estimator import estimate_cost_usd

            run.estimated_cost_usd = estimate_cost_usd(run.model, run.token_usage)
            run.graph_version = GRAPH_VERSION
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
        channel: str | None = None,
    ) -> AIResponse:
        config = await RuntimeAIConfig.resolve(self.db, organization_id, channel)
        state = SupportAgentState(
            organization_id=organization_id,
            conversation_id=conversation_id,
            user_message=message,
            channel=channel,
        )
        if conversation_id:
            state = await ContextBuilder(self.db).build(conversation_id)
            state.user_message = message

        final_state, _latency, _tokens = await timed_support_agent(
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

        conv = await self.db.get(Conversation, msg.conversation_id)
        if conv is None:
            return None

        config = await RuntimeAIConfig.resolve(self.db, conv.organization_id, conv.channel)
        if not config.enabled:
            from app.modules.ai.application.missed_chat_service import MissedChatService

            await MissedChatService(self.db).route_incoming_if_ai_disabled(conv.id, conv.organization_id)
            return None

        from app.infrastructure.database.models import AIControlMode

        if conv.ai_control_mode == AIControlMode.HUMAN_CONTROL:
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
        config: RuntimeAIConfig,
    ) -> None:
        from app.infrastructure.database.models import AIControlMode

        live_config = await RuntimeAIConfig.resolve(
            self.db, state.organization_id or "", state.channel or config.channel
        )
        if not live_config.enabled:
            return

        if state.ai_control_mode == AIControlMode.HUMAN_CONTROL.value:
            return

        mode = live_config.mode

        if mode == AIMode.SUGGEST or response.decision == AgentDecision.SUGGEST_ONLY:
            await self._save_suggestion(state, response, run)
            if response.decision == AgentDecision.ESCALATE or response.escalation_required:
                await EscalationService(self.db).create_from_ai_run(
                    state,
                    organization_id=state.organization_id or "",
                    ai_run_id=run.id,
                    intent_team_map=live_config.intent_team_map,
                    notify_customer=False,
                )
            return

        if mode == AIMode.DRAFT_ONLY:
            if response.decision == AgentDecision.AI_RESOLVE and response.grounded:
                await self._save_ai_reply(state, response, run)
            else:
                await EscalationService(self.db).create_from_ai_run(
                    state,
                    organization_id=state.organization_id or "",
                    ai_run_id=run.id,
                    intent_team_map=live_config.intent_team_map,
                    notify_customer=False,
                )
            return

        if response.decision == AgentDecision.AI_RESOLVE and mode == AIMode.AUTO_REPLY:
            if not response.grounded:
                await EscalationService(self.db).create_from_ai_run(
                    state,
                    organization_id=state.organization_id or "",
                    ai_run_id=run.id,
                    intent_team_map=live_config.intent_team_map,
                )
                return
            await self._save_ai_reply(state, response, run)
        elif response.decision == AgentDecision.ESCALATE and mode == AIMode.AUTO_REPLY:
            await EscalationService(self.db).create_from_ai_run(
                state,
                organization_id=state.organization_id or "",
                ai_run_id=run.id,
                intent_team_map=live_config.intent_team_map,
            )

    async def _save_suggestion(self, state: SupportAgentState, response: AIResponse, run: AIRun) -> None:
        """Store AI suggestion for agent review — never sends customer-facing message."""
        conversations = ConversationService(self.db)
        conv = await conversations.get_conversation_by_id(state.conversation_id or "")
        msg = Message(
            conversation_id=state.conversation_id,
            sender_type=SenderType.SYSTEM,
            sender_id=None,
            content=response.answer,
            metadata_={
                "internal": True,
                "suggestion": True,
                "suggestion_status": "generated",
                "event": "suggestion.generated",
                "ai_run_id": run.id,
                "trigger_message_id": state.message_id,
                "confidence": response.confidence,
                "intent": response.intent.value,
                "grounded": response.grounded,
                "citations": [c.model_dump() for c in response.citations],
            },
        )
        self.db.add(msg)
        await self.db.flush()
        await conversations._publish_message(msg, conv)  # noqa: SLF001

    async def update_suggestion_status(
        self,
        message_id: str,
        status: str,
        *,
        event: str | None = None,
    ) -> Message | None:
        msg = await self.db.get(Message, message_id)
        if msg is None or not msg.metadata_ or not msg.metadata_.get("suggestion"):
            return None
        meta = dict(msg.metadata_)
        meta["suggestion_status"] = status
        if event:
            meta["event"] = event
        msg.metadata_ = meta
        await self.db.flush()
        return msg

    async def _save_ai_reply(self, state: SupportAgentState, response: AIResponse, run: AIRun) -> Message | None:
        if state.message_id and await self._ai_reply_exists(state.message_id):
            return None

        conversations = ConversationService(self.db)
        conv = await conversations.get_conversation_by_id(state.conversation_id or "")
        metadata = {
            "ai_run_id": run.id,
            "trigger_message_id": state.message_id,
            "confidence": response.confidence,
            "intent": response.intent.value,
            "grounded": response.grounded,
            "citations": [c.model_dump() for c in response.citations],
            "ai_status": "AI Resolved",
            "estimated_cost_usd": run.estimated_cost_usd,
        }
        channel = conv.channel
        channel_value = channel.value if hasattr(channel, "value") else str(channel)
        if channel_value == "EMAIL":
            return await conversations.send_ai_reply(state.conversation_id or "", response.answer, metadata)

        msg = Message(
            conversation_id=state.conversation_id,
            sender_type=SenderType.AI,
            sender_id=None,
            content=response.answer,
            channel=conv.channel,
            metadata_=metadata,
        )
        self.db.add(msg)
        await self.db.flush()
        await conversations._publish_message(msg, conv)  # noqa: SLF001
        return msg

    async def _acquire_agent_run(
        self,
        conversation_id: str,
        message_id: str,
        *,
        force: bool = False,
    ) -> tuple[AIRun, bool]:
        """Return an agent run and whether graph execution should be skipped."""
        existing = await self._get_existing_agent_run(message_id)
        if existing is not None and force:
            existing.status = AIRunStatus.PENDING
            existing.error = None
            existing.output = None
            existing.intent = None
            existing.retrieval_count = None
            existing.confidence = None
            existing.latency_ms = None
            existing.token_usage = None
            existing.trace = None
            await self.db.flush()
            return existing, False
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
