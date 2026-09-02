"""Day 5 inbound email + idempotency tests."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.infrastructure.database.models import Conversation, Customer, Message, Organization
from app.infrastructure.database.session import AsyncSessionLocal
from app.main import app
from app.modules.conversations.service import ConversationService


def _sign(body: bytes) -> str:
    return hmac.new(b"mock-secret", body, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_inbound_email_creates_conversation_and_message() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()

    payload = {
        "organization_id": org_id,
        "message_id": f"<inbound-{uuid.uuid4()}@example.com>",
        "from_email": "john@example.com",
        "from_name": "John Doe",
        "to_email": "support@acme.example",
        "subject": "Password Reset",
        "body_text": "I cannot reset my password.",
    }
    body = json.dumps(payload).encode()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/webhooks/email/inbound",
            content=body,
            headers={
                "Content-Type": "application/json",
                "x-mock-signature": _sign(body),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["duplicate"] is False

    async with AsyncSessionLocal() as session:
        conv = await session.get(Conversation, data["conversation_id"])
        assert conv is not None
        assert conv.channel.value == "EMAIL"
        assert conv.subject == "Password Reset"
        msg = await session.get(Message, data["message_id"])
        assert msg is not None
        assert msg.content == "I cannot reset my password."
        customer = await session.get(Customer, conv.customer_id)
        assert customer is not None
        assert customer.email == "john@example.com"


@pytest.mark.asyncio
async def test_duplicate_webhook_is_idempotent() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()

    payload = {
        "organization_id": org_id,
        "message_id": "<duplicate-test@example.com>",
        "from_email": "dup@example.com",
        "subject": "Billing",
        "body_text": "Question about billing",
    }
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "x-mock-signature": _sign(body)}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post("/api/v1/webhooks/email/inbound", content=body, headers=headers)
        r2 = await client.post("/api/v1/webhooks/email/inbound", content=body, headers=headers)
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r2.json()["duplicate"] is True

    async with AsyncSessionLocal() as session:
        count = (
            await session.execute(
                select(func.count(Message.id)).where(Message.external_message_id == "<duplicate-test@example.com>")
            )
        ).scalar_one()
        assert count == 1
        conv_count = (
            await session.execute(
                select(func.count(Conversation.id)).join(Customer).where(Customer.email == "dup@example.com")
            )
        ).scalar_one()
        assert conv_count == 1
