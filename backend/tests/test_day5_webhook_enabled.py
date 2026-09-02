"""Day 5 webhook channel enabled gate."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.infrastructure.database.models import ChannelConfiguration, ChannelType, Organization
from app.infrastructure.database.session import AsyncSessionLocal
from app.main import app


@pytest.mark.asyncio
async def test_webhook_rejects_disabled_email_channel() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        cfg = await session.scalar(
            select(ChannelConfiguration).where(
                ChannelConfiguration.organization_id == org_id,
                ChannelConfiguration.channel == ChannelType.EMAIL,
            )
        )
        assert cfg is not None
        cfg.enabled = False
        await session.commit()

    payload = {
        "organization_id": org_id,
        "message_id": "<disabled-channel@example.com>",
        "from_email": "disabled@example.com",
        "subject": "Should fail",
        "body_text": "Channel disabled",
    }

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/webhooks/email/inbound",
                json=payload,
                headers={"x-mock-signature": "test-bypass"},
            )
            assert resp.status_code == 403
    finally:
        async with AsyncSessionLocal() as session:
            cfg = await session.scalar(
                select(ChannelConfiguration).where(
                    ChannelConfiguration.organization_id == org_id,
                    ChannelConfiguration.channel == ChannelType.EMAIL,
                )
            )
            if cfg is not None:
                cfg.enabled = True
                await session.commit()
