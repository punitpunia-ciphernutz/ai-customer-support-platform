"""Day 6 notification tests."""

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import Organization, Role, RoleName, User
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.notifications.application.service import NotificationService
from app.modules.notifications.domain.models import Notification


@pytest.mark.asyncio
async def test_notify_managers_creates_in_app_notification() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        manager = await session.scalar(
            select(User)
            .join(Role, User.role_id == Role.id)
            .where(User.organization_id == org_id, Role.name == RoleName.MANAGER)
        )
        if manager is None:
            pytest.skip("Manager user not seeded")

        count = await NotificationService(session).notify_managers(
            organization_id=org_id,
            event_type="MANAGER_ALERT",
            title="Test alert",
            body="Angry customer",
        )
        await session.commit()

        assert count >= 1
        note = await session.scalar(select(Notification).where(Notification.user_id == manager.id))
        assert note is not None
        assert note.title == "Test alert"
