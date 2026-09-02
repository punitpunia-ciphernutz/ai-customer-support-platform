"""Resolve org AI config with optional per-channel BotConfiguration overrides."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.application.ai_config_service import get_or_create_ai_config
from app.modules.ai.domain.models import AIConfig, AIMode, BotConfiguration


@dataclass(frozen=True)
class RuntimeAIConfig:
    """Effective AI settings for a single pipeline run (org default + channel override)."""

    enabled: bool
    mode: AIMode
    auto_reply_threshold: float
    escalation_threshold: float
    min_relevance_score: float
    require_knowledge: bool
    escalate_if_unknown: bool
    multilingual_enabled: bool
    hybrid_keyword_weight: float
    missed_chat_timeout_minutes: int
    ai_response_timeout_seconds: int
    allowed_intents: list[str] | None
    restricted_intents: list[str] | None
    intent_team_map: dict[str, str] | None
    organization_id: str
    channel: str | None = None

    @classmethod
    async def resolve(
        cls,
        db: AsyncSession,
        organization_id: str,
        channel: str | None = None,
    ) -> RuntimeAIConfig:
        base = await get_or_create_ai_config(db, organization_id)
        override: BotConfiguration | None = None
        channel_key = channel.value if hasattr(channel, "value") else channel
        if channel_key:
            override = await db.scalar(
                select(BotConfiguration).where(
                    BotConfiguration.organization_id == organization_id,
                    BotConfiguration.channel == channel_key,
                )
            )
        return cls.from_config(base, override, channel_key)

    @classmethod
    def from_config(
        cls,
        base: AIConfig,
        override: BotConfiguration | None = None,
        channel: str | None = None,
    ) -> RuntimeAIConfig:
        def pick(field: str, default: Any) -> Any:
            if override is None:
                return default
            value = getattr(override, field, None)
            return default if value is None else value

        return cls(
            enabled=base.enabled,
            mode=pick("mode", base.mode),
            auto_reply_threshold=pick("auto_reply_threshold", base.auto_reply_threshold),
            escalation_threshold=pick("escalation_threshold", base.escalation_threshold),
            min_relevance_score=pick("min_relevance_score", base.min_relevance_score),
            require_knowledge=pick("require_knowledge", base.require_knowledge),
            escalate_if_unknown=base.escalate_if_unknown,
            multilingual_enabled=pick("multilingual_enabled", base.multilingual_enabled),
            hybrid_keyword_weight=base.hybrid_keyword_weight,
            missed_chat_timeout_minutes=base.missed_chat_timeout_minutes,
            ai_response_timeout_seconds=base.ai_response_timeout_seconds,
            allowed_intents=base.allowed_intents,
            restricted_intents=base.restricted_intents,
            intent_team_map=base.intent_team_map,
            organization_id=base.organization_id,
            channel=channel,
        )
