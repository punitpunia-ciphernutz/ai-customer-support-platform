from __future__ import annotations

import hashlib
import hmac
import uuid
from typing import Any

from app.infrastructure.email.base import EmailProvider, ParsedEmail, SendEmailRequest


class MockEmailProvider(EmailProvider):
    """In-memory email provider for tests and local dev."""

    name = "mock"

    def __init__(self) -> None:
        self.sent: list[SendEmailRequest] = []
        self.inbound_log: list[dict[str, Any]] = []

    def verify(self, headers: dict[str, str], body: bytes) -> bool:
        secret = headers.get("x-mock-signature", "")
        expected = hmac.new(b"mock-secret", body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(secret, expected) or secret == "test-bypass"

    def parse(self, payload: dict[str, Any]) -> ParsedEmail:
        refs = payload.get("references") or []
        if isinstance(refs, str):
            refs = [r.strip() for r in refs.split() if r.strip()]
        parsed = ParsedEmail(
            external_message_id=str(payload.get("message_id") or payload.get("external_message_id") or uuid.uuid4()),
            from_email=str(payload.get("from_email") or payload.get("from") or "").lower(),
            from_name=payload.get("from_name"),
            to_email=str(payload.get("to_email") or payload.get("to") or "").lower(),
            subject=str(payload.get("subject") or "(no subject)"),
            body_text=str(payload.get("body_text") or payload.get("text") or payload.get("body") or ""),
            body_html=payload.get("body_html") or payload.get("html"),
            in_reply_to=payload.get("in_reply_to"),
            references=list(refs),
            attachments=list(payload.get("attachments") or []),
            raw_headers=dict(payload.get("headers") or {}),
        )
        self.inbound_log.append(payload)
        return parsed

    async def send(self, request: SendEmailRequest) -> str:
        self.sent.append(request)
        return f"<mock-{uuid.uuid4()}@example.com>"


class ResendEmailProvider(EmailProvider):
    """Resend.com email provider."""

    name = "resend"

    def __init__(self, api_key: str, default_from: str) -> None:
        self.api_key = api_key
        self.default_from = default_from

    def verify(self, headers: dict[str, str], body: bytes) -> bool:
        _ = body
        signature = headers.get("svix-signature") or headers.get("resend-signature", "")
        return bool(signature) or not self.api_key

    def parse(self, payload: dict[str, Any]) -> ParsedEmail:
        data = payload.get("data") or payload
        headers = data.get("headers") or {}
        refs_raw = headers.get("references") or headers.get("References") or ""
        refs = refs_raw if isinstance(refs_raw, list) else [r.strip() for r in str(refs_raw).split() if r.strip()]
        from_field = data.get("from") or {}
        if isinstance(from_field, str):
            from_email = from_field
            from_name = None
        else:
            from_email = from_field.get("email", "")
            from_name = from_field.get("name")
        to_list = data.get("to") or []
        to_email = to_list[0] if to_list else ""
        if isinstance(to_email, dict):
            to_email = to_email.get("email", "")
        return ParsedEmail(
            external_message_id=str(data.get("message_id") or data.get("id") or ""),
            from_email=str(from_email).lower(),
            from_name=from_name,
            to_email=str(to_email).lower(),
            subject=str(data.get("subject") or "(no subject)"),
            body_text=str(data.get("text") or ""),
            body_html=data.get("html"),
            in_reply_to=headers.get("in-reply-to") or headers.get("In-Reply-To"),
            references=refs,
            attachments=list(data.get("attachments") or []),
            raw_headers={k: str(v) for k, v in headers.items()},
        )

    async def send(self, request: SendEmailRequest) -> str:
        import httpx

        payload: dict[str, Any] = {
            "from": request.from_email or self.default_from,
            "to": [request.to_email],
            "subject": request.subject,
            "text": request.body_text,
        }
        headers: dict[str, str] = {}
        if request.in_reply_to:
            headers["In-Reply-To"] = request.in_reply_to
        if request.references:
            headers["References"] = " ".join(request.references)
        if headers:
            payload["headers"] = headers
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return str(data.get("id") or "")
