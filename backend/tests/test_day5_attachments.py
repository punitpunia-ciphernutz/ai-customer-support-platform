"""Day 5 attachment tests."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.infrastructure.database.models import Organization, User
from app.infrastructure.database.session import AsyncSessionLocal
from app.main import app
from app.modules.attachments.service import AttachmentService
from app.modules.auth.security import create_access_token


async def _auth_headers() -> dict[str, str]:
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).limit(1))).scalar_one()
        token = create_access_token(user.id, {"organization_id": user.organization_id})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_upload_attachment() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        attachment = await AttachmentService(session).upload(
            organization_id=org_id,
            filename="test.txt",
            mime_type="text/plain",
            data=b"hello attachment",
        )
        assert attachment.filename == "test.txt"
        assert attachment.size == 16
        url = await AttachmentService(session).get_download_url(attachment)
        assert url == f"/api/v1/attachments/{attachment.id}/download"
        await session.rollback()


@pytest.mark.asyncio
async def test_download_attachment_via_http() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        attachment = await AttachmentService(session).upload(
            organization_id=org_id,
            filename="invoice.txt",
            mime_type="text/plain",
            data=b"invoice details",
        )
        attachment_id = attachment.id
        await session.commit()

    headers = await _auth_headers()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        meta = await client.get(f"/api/v1/attachments/{attachment_id}", headers=headers)
        assert meta.status_code == 200
        assert meta.json()["download_url"] == f"/api/v1/attachments/{attachment_id}/download"

        resp = await client.get(f"/api/v1/attachments/{attachment_id}/download", headers=headers)
        assert resp.status_code == 200
        assert resp.content == b"invoice details"
        assert "invoice.txt" in resp.headers.get("content-disposition", "")

        unauth = await client.get(f"/api/v1/attachments/{attachment_id}/download")
        assert unauth.status_code == 401
