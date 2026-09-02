"""ChannelAdapter unit tests."""

import pytest

from app.infrastructure.database.models import ChannelType
from app.modules.conversations.channels import EmailAdapter, WebChatAdapter, get_adapter
from app.modules.conversations.normalizer import normalize_subject


@pytest.mark.asyncio
async def test_webchat_normalize_and_identify() -> None:
    adapter = WebChatAdapter()
    incoming = await adapter.normalize(
        {
            "organization_id": "org-1",
            "content": "  Hello, I need help.  ",
            "customer_id": "cust-1",
            "customer_email": "a@b.com",
            "customer_name": "Ada",
            "metadata": {"page": "/help"},
        }
    )
    assert incoming.channel == ChannelType.WEB_CHAT
    assert incoming.content == "Hello, I need help."
    assert incoming.customer_id == "cust-1"
    identified = await adapter.identify_customer(incoming)
    assert identified.customer_id == "cust-1"
    received = await adapter.receive(
        {"organization_id": "org-1", "content": "ping", "customer_id": "cust-1"}
    )
    assert received.content == "ping"
    await adapter.send("conv-1", "reply")


def test_get_adapter_web_chat() -> None:
    assert get_adapter(ChannelType.WEB_CHAT).channel == ChannelType.WEB_CHAT


@pytest.mark.asyncio
async def test_email_adapter_normalize() -> None:
    adapter = EmailAdapter()
    incoming = await adapter.normalize(
        {
            "organization_id": "org-1",
            "from_email": "john@example.com",
            "subject": "Re: Billing",
            "body_text": "Still waiting on refund.",
            "external_message_id": "<msg-1@example.com>",
        }
    )
    assert incoming.channel == ChannelType.EMAIL
    assert incoming.customer_email == "john@example.com"
    assert incoming.external_id == "<msg-1@example.com>"
    assert incoming.metadata["subject"] == "Re: Billing"


def test_normalize_subject() -> None:
    assert normalize_subject("Re: Fwd: Billing Issue") == "billing issue"
