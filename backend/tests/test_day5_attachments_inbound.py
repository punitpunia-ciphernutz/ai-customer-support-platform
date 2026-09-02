"""Day 5 inbound attachment storage tests."""

import base64
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.infrastructure.database.models import Attachment, Message, Organization
from app.infrastructure.database.session import AsyncSessionLocal
from app.main import app


@pytest.mark.asyncio
async def test_inbound_email_stores_attachments() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()

    content_b64 = base64.b64encode(b"invoice details").decode("ascii")
    payload = {
        "organization_id": org_id,
        "message_id": f"<attach-{uuid.uuid4()}@example.com>",
        "from_email": "attach@example.com",
        "subject": "Invoice attached",
        "body_text": "See attached invoice.",
        "attachments": [
            {
                "filename": "invoice.txt",
                "mime_type": "text/plain",
                "content_base64": content_b64,
            }
        ],
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/webhooks/email/inbound",
            json=payload,
            headers={"x-mock-signature": "test-bypass"},
        )
        assert resp.status_code == 200
        message_id = resp.json()["message_id"]

    async with AsyncSessionLocal() as session:
        attachments = (
            await session.execute(select(Attachment).where(Attachment.message_id == message_id))
        ).scalars().all()
        assert len(attachments) == 1
        assert attachments[0].filename == "invoice.txt"
        msg = await session.get(Message, message_id)
        assert msg is not None
