"""DB-backed prompt versioning and template rendering."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.application.context_builder import format_history_for_prompt
from app.modules.ai.domain.models import Prompt, PromptVersion
from app.modules.ai.domain.schemas import SupportAgentState
from app.modules.ai.prompts.support_agent_v1 import render_generate_prompt as render_file_generate_prompt


class PromptService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_active(self, name: str) -> PromptVersion | None:
        prompt = await self.db.scalar(select(Prompt).where(Prompt.name == name))
        if prompt is None:
            return None
        return await self.db.scalar(
            select(PromptVersion).where(PromptVersion.prompt_id == prompt.id, PromptVersion.active.is_(True))
        )

    def version_label(self, name: str, version: int) -> str:
        return f"{name}:v{version}"

    async def render_support_agent_prompt(self, state: SupportAgentState) -> tuple[str, str]:
        """Return (prompt_text, prompt_version_label). Falls back to file renderer."""
        version = await self.get_active("support_agent_system")
        if version is None:
            return render_file_generate_prompt(state), "support-agent-v2-file"

        knowledge_blocks = [f"### {doc.title}\n{doc.content}" for doc in state.retrieved_documents]
        knowledge = "\n\n".join(knowledge_blocks) if knowledge_blocks else "(no relevant knowledge found)"

        customer = state.customer_context
        if customer:
            parts = [f"Name: {customer.name}"]
            if customer.email:
                parts.append(f"Email: {customer.email}")
            if customer.company:
                parts.append(f"Company: {customer.company}")
            customer_text = "\n".join(parts)
        else:
            customer_text = "Unknown customer"

        history = format_history_for_prompt(state.conversation_history)
        summary = state.conversation_summary or "(no summary yet)"
        message = state.user_message

        template = version.template
        rendered = (
            template.replace("{{knowledge}}", knowledge)
            .replace("{{customer}}", customer_text)
            .replace("{{summary}}", summary)
            .replace("{{history}}", history)
            .replace("{{message}}", message)
        )
        label = self.version_label("support_agent_system", version.version)
        return rendered, label

    async def render_grounding_prompt(self, answer: str, knowledge_text: str) -> str:
        version = await self.get_active("grounding_validator")
        if version is None:
            return (
                "You are a grounding validator. Given retrieved knowledge and a generated answer, "
                "determine if the answer is supported by the knowledge.\n\n"
                f"KNOWLEDGE:\n{knowledge_text or '(none)'}\n\n"
                f"ANSWER:\n{answer}\n\n"
                'Respond with JSON: {"grounded": <bool>, "score": <0.0-1.0>, "unsupported_claims": [<string>]}'
            )
        return version.template.replace("{{knowledge}}", knowledge_text or "(none)").replace("{{answer}}", answer)
