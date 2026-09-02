"""Day 5 PATCH per-channel bot configuration tests."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.infrastructure.database.models import Organization
from app.infrastructure.database.session import AsyncSessionLocal
from app.main import app
from app.modules.ai.domain.models import AIMode, BotConfiguration


@pytest.mark.asyncio
async def test_patch_ai_config_channel_override() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post("/api/v1/auth/login", json={"email": "agent@example.com", "password": "agent123!"})
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.patch(
            "/api/v1/ai/config",
            headers=headers,
            json={"channel_overrides": [{"channel": "EMAIL", "mode": "AUTO_REPLY"}]},
        )
        assert resp.status_code == 200
        overrides = resp.json()["channel_overrides"]
        email = next(o for o in overrides if o["channel"] == "EMAIL")
        assert email["mode"] == "AUTO_REPLY"

    async with AsyncSessionLocal() as session:
        bot = await session.scalar(
            select(BotConfiguration).where(
                BotConfiguration.organization_id == org_id,
                BotConfiguration.channel == "EMAIL",
            )
        )
        assert bot is not None
        assert bot.mode == AIMode.AUTO_REPLY
        bot.mode = AIMode.SUGGEST
        await session.commit()
