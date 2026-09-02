"""Day 5 attachment tests."""

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import Organization
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.attachments.service import AttachmentService


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
        assert url
        await session.rollback()
