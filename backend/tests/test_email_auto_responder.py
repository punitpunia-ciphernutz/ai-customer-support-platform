"""Email auto-responder for new inbound threads."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.infrastructure.database.models import (
    ChannelConfiguration,
    ChannelType,
    Message,
    Organization,
    SenderType,
)
from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.email import get_mock_email_provider
from app.main import app
from app.modules.channels.auto_responder import (
    is_auto_submitted_or_bounce,
    render_template,
)


def _sign(body: bytes) -> str:
    return hmac.new(b"mock-secret", body, hashlib.sha256).hexdigest()


async def _enable_auto_reply(org_id: str, *, subject: str, body: str) -> None:
    async with AsyncSessionLocal() as session:
        cfg = (
            await session.execute(
                select(ChannelConfiguration).where(
                    ChannelConfiguration.organization_id == org_id,
                    ChannelConfiguration.channel == ChannelType.EMAIL,
                )
            )
        ).scalar_one_or_none()
        if cfg is None:
            cfg = ChannelConfiguration(
                organization_id=org_id,
                channel=ChannelType.EMAIL,
                enabled=True,
                provider="mock",
                settings={},
            )
            session.add(cfg)
            await session.flush()
        settings = dict(cfg.settings or {})
        settings.update(
            {
                "email_auto_reply_enabled": True,
                "email_auto_reply_subject": subject,
                "email_auto_reply_body": body,
            }
        )
        cfg.settings = settings
        cfg.enabled = True
        await session.commit()


def test_render_template_placeholders() -> None:
    out = render_template(
        "Hi {{customer_name}} — {{subject}} / {{conversation_id}}",
        {"customer_name": "Ada", "subject": "Help", "conversation_id": "c1", "ticket_id": ""},
    )
    assert out == "Hi Ada — Help / c1"


def test_auto_submitted_detection() -> None:
    assert is_auto_submitted_or_bounce({"Auto-Submitted": "auto-replied"})
    assert is_auto_submitted_or_bounce({"Precedence": "bulk"})
    assert not is_auto_submitted_or_bounce({"Auto-Submitted": "no"})
    assert not is_auto_submitted_or_bounce({})


@pytest.mark.asyncio
async def test_auto_reply_sends_on_first_inbound_only() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()

    await _enable_auto_reply(
        org_id,
        subject="Ack: {{subject}}",
        body="Hello {{customer_name}}, we got it.",
    )

    provider = get_mock_email_provider()
    provider.sent.clear()

    unique = uuid.uuid4().hex[:8]
    customer_email = f"auto.customer.{unique}@example.com"
    first_payload = {
        "organization_id": org_id,
        "message_id": f"<auto-reply-first-{unique}@example.com>",
        "from_email": customer_email,
        "from_name": "Auto Customer",
        "to_email": "support@acme.example",
        "subject": f"Need help {unique}",
        "body_text": "Please help me.",
    }
    body = json.dumps(first_payload).encode()
    headers = {"Content-Type": "application/json", "x-mock-signature": _sign(body)}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post("/api/v1/webhooks/email/inbound", content=body, headers=headers)
        assert r1.status_code == 200
        conv_id = r1.json()["conversation_id"]

        follow = {
            **first_payload,
            "message_id": f"<auto-reply-follow-{unique}@example.com>",
            "in_reply_to": first_payload["message_id"],
            "references": [first_payload["message_id"]],
            "body_text": "Following up.",
        }
        body2 = json.dumps(follow).encode()
        r2 = await client.post(
            "/api/v1/webhooks/email/inbound",
            content=body2,
            headers={"Content-Type": "application/json", "x-mock-signature": _sign(body2)},
        )
        assert r2.status_code == 200
        assert r2.json()["conversation_id"] == conv_id

    auto_sends = [s for s in provider.sent if s.headers.get("Auto-Submitted") == "auto-replied"]
    assert len(auto_sends) == 1
    assert auto_sends[0].to_email == customer_email
    assert auto_sends[0].subject == f"Ack: Need help {unique}"
    assert "Hello Auto Customer" in auto_sends[0].body_text

    async with AsyncSessionLocal() as session:
        system_count = (
            await session.execute(
                select(func.count(Message.id)).where(
                    Message.conversation_id == conv_id,
                    Message.sender_type == SenderType.SYSTEM,
                    Message.metadata_.contains({"auto_responder": True}),
                )
            )
        ).scalar_one()
        assert system_count == 1


@pytest.mark.asyncio
async def test_auto_reply_skips_auto_submitted_inbound() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()

    await _enable_auto_reply(
        org_id,
        subject="Should not send",
        body="Should not send",
    )

    provider = get_mock_email_provider()
    before = len(provider.sent)
    unique = uuid.uuid4().hex[:8]

    payload = {
        "organization_id": org_id,
        "message_id": f"<auto-submitted-{unique}@example.com>",
        "from_email": f"bot.{unique}@example.com",
        "to_email": "support@acme.example",
        "subject": f"OOO {unique}",
        "body_text": "Out of office",
        "headers": {"Auto-Submitted": "auto-replied"},
    }
    body = json.dumps(payload).encode()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/webhooks/email/inbound",
            content=body,
            headers={"Content-Type": "application/json", "x-mock-signature": _sign(body)},
        )
        assert resp.status_code == 200

    auto_sends = [
        s
        for s in provider.sent[before:]
        if s.headers.get("Auto-Submitted") == "auto-replied" and s.subject == "Should not send"
    ]
    assert auto_sends == []

@pytest.mark.asyncio
async def test_channels_patch_merges_auto_reply_settings() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        cfg = (
            await session.execute(
                select(ChannelConfiguration).where(
                    ChannelConfiguration.organization_id == org_id,
                    ChannelConfiguration.channel == ChannelType.EMAIL,
                )
            )
        ).scalar_one_or_none()
        if cfg is None:
            cfg = ChannelConfiguration(
                organization_id=org_id,
                channel=ChannelType.EMAIL,
                enabled=True,
                provider="mock",
                settings={"from_address": "support@acme.example"},
            )
            session.add(cfg)
        else:
            cfg.settings = {**(cfg.settings or {}), "from_address": "support@acme.example"}
        await session.commit()

    from app.infrastructure.database.models import Role, RoleName, User
    from app.modules.auth.security import create_access_token
    from sqlalchemy.orm import selectinload

    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(
                select(User)
                .join(Role, Role.id == User.role_id)
                .where(
                    User.organization_id == org_id,
                    Role.name == RoleName.ADMIN,
                    User.is_active.is_(True),
                )
                .options(selectinload(User.role))
                .limit(1)
            )
        ).scalar_one()
        token = create_access_token(user.id, {"organization_id": user.organization_id})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.patch(
            "/api/v1/channels/EMAIL",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "settings": {
                    "email_auto_reply_enabled": True,
                    "email_auto_reply_subject": "Thanks",
                    "email_auto_reply_body": "Got it",
                }
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["settings"]["from_address"] == "support@acme.example"
        assert data["settings"]["email_auto_reply_enabled"] is True
        assert data["settings"]["email_auto_reply_subject"] == "Thanks"
