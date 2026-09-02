"""Versioned prompts for the Day 3 support agent."""

from __future__ import annotations

from app.modules.ai.domain.schemas import SupportAgentState
from app.modules.ai.application.context_builder import format_history_for_prompt

PROMPT_VERSION = "support-agent-v2"


def render_rerank_prompt(query: str, title: str, content: str) -> str:
    return (
        "Rate how relevant this knowledge chunk is to the customer question on a scale of 0.0 to 1.0.\n"
        f"Question: {query}\n"
        f"Title: {title}\n"
        f"Content: {content[:1200]}\n"
        "Respond with JSON: {\"relevance\": <float>}"
    )


def render_generate_prompt(state: SupportAgentState) -> str:
    knowledge_blocks = []
    for doc in state.retrieved_documents:
        knowledge_blocks.append(f"### {doc.title}\n{doc.content}")
    knowledge_section = "\n\n".join(knowledge_blocks) if knowledge_blocks else "(no relevant knowledge found)"

    customer = state.customer_context
    customer_section = "Unknown customer"
    if customer:
        parts = [f"Name: {customer.name}"]
        if customer.email:
            parts.append(f"Email: {customer.email}")
        if customer.company:
            parts.append(f"Company: {customer.company}")
        customer_section = "\n".join(parts)

    history_section = format_history_for_prompt(state.conversation_history)
    summary_section = state.conversation_summary or "(no summary yet)"
    prev_ai_section = (
        "\n".join(f"- {r}" for r in state.previous_ai_responses)
        if state.previous_ai_responses
        else "(none)"
    )
    ticket_section = "(no open ticket)"
    if state.ticket_context:
        ticket_section = (
            f"Ticket {state.ticket_context.get('ticket_id')}: "
            f"status={state.ticket_context.get('status')}, "
            f"priority={state.ticket_context.get('priority')}"
        )

    return f"""SYSTEM:
You are a helpful customer support agent for the company.
Answer using ONLY the provided company knowledge when answering product/policy questions.
Rules:
- Do not invent company-specific information.
- If the knowledge does not contain the answer, say you do not have enough information.
- Do not claim an action was performed unless a tool actually performed it.
- Keep the response concise and friendly.
- Ask for clarification when the question is ambiguous.
- Reply in the same language as the customer's current message when possible.

COMPANY KNOWLEDGE:
{knowledge_section}

CUSTOMER:
{customer_section}

CONVERSATION SUMMARY:
{summary_section}

PREVIOUS AI RESPONSES:
{prev_ai_section}

TICKET CONTEXT:
{ticket_section}

CONVERSATION (recent):
{history_section}

CURRENT MESSAGE:
{state.user_message}
"""


def render_escalation_summary_prompt(state: SupportAgentState) -> str:
    docs = ", ".join(d.title for d in state.retrieved_documents) or "None"
    return (
        "Write a brief internal escalation summary for a human agent (2-4 sentences).\n"
        f"Customer message: {state.user_message}\n"
        f"Intent: {state.intent}\n"
        f"Confidence: {state.support_confidence:.2f}\n"
        f"Reason: {state.escalation_reason}\n"
        f"Knowledge searched: {docs}\n"
        f"Draft response (not sent): {state.draft_response or 'None'}\n"
    )
