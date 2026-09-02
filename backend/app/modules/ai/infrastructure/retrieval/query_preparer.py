"""Intent-enriched query preparation for hybrid retrieval."""

from __future__ import annotations

from app.modules.ai.domain.schemas import IntentLabel, SupportAgentState


class QueryPreparer:
    @staticmethod
    def prepare(state: SupportAgentState) -> str:
        query = state.user_message.strip()
        if not query:
            return query

        parts = [query]
        if state.intent == IntentLabel.ACCOUNT_ACCESS and "password" not in query.lower():
            parts.append("password account access login")
        elif state.intent == IntentLabel.BILLING:
            parts.append("billing invoice payment plan")
        elif state.intent == IntentLabel.TECHNICAL_ISSUE:
            parts.append("troubleshooting error technical")

        if state.language and state.language != "en":
            parts.append(f"language:{state.language}")

        return " ".join(parts)
