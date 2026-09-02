"""Organization AI configuration service."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.domain.models import AIConfig, AIMode
from app.modules.ai.domain.schemas import AIConfigUpdate


async def get_or_create_ai_config(db: AsyncSession, organization_id: str) -> AIConfig:
    result = await db.execute(select(AIConfig).where(AIConfig.organization_id == organization_id))
    config = result.scalar_one_or_none()
    if config is not None:
        return config
    config = AIConfig(
        organization_id=organization_id,
        enabled=True,
        mode=AIMode.AUTO_REPLY,
        auto_reply_threshold=0.85,
        escalation_threshold=0.85,
        min_relevance_score=0.35,
        require_knowledge=True,
        escalate_if_unknown=True,
        multilingual_enabled=True,
        hybrid_keyword_weight=0.3,
        missed_chat_timeout_minutes=5,
        restricted_intents=["OTHER"],
        intent_team_map={
            "BILLING": "Billing",
            "REFUND": "Billing",
            "CANCELLATION": "Billing",
        },
    )
    db.add(config)
    await db.flush()
    return config


async def update_ai_config(db: AsyncSession, organization_id: str, body: AIConfigUpdate) -> AIConfig:
    config = await get_or_create_ai_config(db, organization_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(config, key, value)
    await db.flush()
    await db.refresh(config)
    return config
