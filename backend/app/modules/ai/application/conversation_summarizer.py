"""Conversation summarization for token-efficient memory."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.infrastructure.database.models import Conversation, Message, SenderType
from app.modules.ai.application.context_builder import format_history_for_prompt
from app.modules.ai.domain.schemas import ConversationTurn
from app.modules.ai.infrastructure.llm.providers import LLMProvider, get_llm_provider


class ConversationSummarizer:
    """Generate or refresh a rolling conversation summary when message count exceeds threshold."""

    def __init__(self, db: AsyncSession, llm: LLMProvider | None = None) -> None:
        self.db = db
        self.llm = llm or get_llm_provider()
        self.settings = get_settings()

    async def summarize_if_needed(self, conversation_id: str) -> str | None:
        result = await self.db.execute(select(Conversation).where(Conversation.id == conversation_id))
        conversation = result.scalar_one_or_none()
        if conversation is None:
            return None

        msgs_result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        messages = list(msgs_result.scalars().all())
        threshold = self.settings.ai_summary_message_threshold
        if len(messages) < threshold:
            return conversation.conversation_summary

        # Refresh when message count crosses another threshold boundary
        if conversation.conversation_summary and len(messages) % threshold != 0:
            return conversation.conversation_summary

        turns = [
            ConversationTurn(sender_type=m.sender_type.value, content=m.content)
            for m in messages[-threshold:]
        ]
        history_text = format_history_for_prompt(turns)
        prior = conversation.conversation_summary or ""

        prompt = (
            "Summarize this customer support conversation in 3-5 sentences. "
            "Focus on the issue, what was tried, and current status. "
            "Do not include sensitive data.\n\n"
        )
        if prior:
            prompt += f"Previous summary:\n{prior}\n\n"
        prompt += f"Recent messages:\n{history_text}"

        summary = await self._generate_summary(prompt)
        conversation.conversation_summary = summary
        await self.db.flush()
        return summary

    async def _generate_summary(self, prompt: str) -> str:
        try:
            result = await self.llm.generate(prompt, max_tokens=256)
            text = (result or "").strip()
            return text[:2000] if text else "(conversation in progress)"
        except Exception:  # noqa: BLE001
            return "(conversation in progress)"
