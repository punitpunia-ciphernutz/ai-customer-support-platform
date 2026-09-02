from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import ChannelConfiguration, ChannelType


class ChannelService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_channels(self, organization_id: str) -> list[ChannelConfiguration]:
        result = await self.db.execute(
            select(ChannelConfiguration)
            .where(ChannelConfiguration.organization_id == organization_id)
            .order_by(ChannelConfiguration.channel.asc())
        )
        configs = list(result.scalars().all())
        existing = {c.channel for c in configs}
        for channel in ChannelType:
            if channel not in existing:
                cfg = ChannelConfiguration(
                    organization_id=organization_id,
                    channel=channel,
                    enabled=channel == ChannelType.WEB_CHAT,
                    provider="mock" if channel == ChannelType.EMAIL else None,
                    settings={},
                )
                self.db.add(cfg)
                configs.append(cfg)
        await self.db.flush()
        return configs

    async def get_channel(self, organization_id: str, channel: ChannelType) -> ChannelConfiguration:
        configs = await self.list_channels(organization_id)
        for cfg in configs:
            if cfg.channel == channel:
                return cfg
        raise ValueError(f"Channel {channel} not found")

    async def update_channel(
        self,
        organization_id: str,
        channel: ChannelType,
        *,
        enabled: bool | None = None,
        provider: str | None = None,
        settings: dict | None = None,
    ) -> ChannelConfiguration:
        cfg = await self.get_channel(organization_id, channel)
        if enabled is not None:
            cfg.enabled = enabled
        if provider is not None:
            cfg.provider = provider
        if settings is not None:
            cfg.settings = settings
        await self.db.flush()
        await self.db.refresh(cfg)
        return cfg
