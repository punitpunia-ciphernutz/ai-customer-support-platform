"""Organization AI configuration service."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.domain.models import AIConfig, AIMode, BotConfiguration
from app.modules.ai.domain.schemas import AIConfigUpdate, BotConfigurationUpdate


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


async def _upsert_bot_configuration(
    db: AsyncSession,
    organization_id: str,
    override: BotConfigurationUpdate,
) -> BotConfiguration:
    bot = await db.scalar(
        select(BotConfiguration).where(
            BotConfiguration.organization_id == organization_id,
            BotConfiguration.channel == override.channel,
        )
    )
    if bot is None:
        bot = BotConfiguration(organization_id=organization_id, channel=override.channel)
        db.add(bot)
        await db.flush()

    data = override.model_dump(exclude_unset=True, exclude={"channel"})
    for key, value in data.items():
        setattr(bot, key, value)
    await db.flush()
    await db.refresh(bot)
    return bot


async def update_ai_config(db: AsyncSession, organization_id: str, body: AIConfigUpdate) -> AIConfig:
    config = await get_or_create_ai_config(db, organization_id)
    payload = body.model_dump(exclude_unset=True)
    channel_overrides = payload.pop("channel_overrides", None)

    for key, value in payload.items():
        setattr(config, key, value)
    await db.flush()

    if channel_overrides is not None:
        for override_data in channel_overrides:
            await _upsert_bot_configuration(
                db,
                organization_id,
                BotConfigurationUpdate.model_validate(override_data),
            )

    await db.refresh(config)
    return config
