"""Prompt templates for the support agent."""

from app.modules.ai.prompts.support_agent_v1 import (
    PROMPT_VERSION,
    render_escalation_summary_prompt,
    render_generate_prompt,
    render_rerank_prompt,
)

__all__ = [
    "PROMPT_VERSION",
    "render_escalation_summary_prompt",
    "render_generate_prompt",
    "render_rerank_prompt",
]
