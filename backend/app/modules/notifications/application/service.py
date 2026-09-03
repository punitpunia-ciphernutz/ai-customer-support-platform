"""Notification delivery."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import RoleName, Team, TeamMember, User
from app.infrastructure.events import DomainEvent, event_bus
from app.modules.notifications.domain.models import Notification, NotificationPreference


logger = logging.getLogger(__name__)

DEFAULT_EVENT_TYPES = (
    "TICKET_ASSIGNED",
    "CONVERSATION_ASSIGNED",
    "AUTOMATION_NOTIFY",
    "MANAGER_ALERT",
    "MISSED_CHAT",
)


class NotificationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def notify(
        self,
        *,
        user_id: str,
        organization_id: str,
        event_type: str,
        title: str,
        body: str,
        metadata: dict[str, Any] | None = None,
    ) -> Notification | None:
        pref = await self._get_preference(user_id, event_type)
        if pref is not None and not pref.enabled:
            return None
        in_app = pref.in_app if pref else True
        send_email = pref.email if pref else False
        if not in_app and not send_email:
            return None
        if send_email and not in_app:
            self._send_email_stub(user_id=user_id, event_type=event_type, title=title, body=body)
            return None
        notification = Notification(
            user_id=user_id,
            organization_id=organization_id,
            event_type=event_type,
            title=title,
            body=body,
            metadata_=metadata or {},
        )
        self.db.add(notification)
        await self.db.flush()
        await event_bus.publish(
            DomainEvent(
                name="notification.created",
                organization_id=organization_id,
                payload={
                    "notification_id": notification.id,
                    "user_id": user_id,
                    "event_type": event_type,
                    "title": title,
                    "body": body,
                },
            )
        )
        if send_email:
            self._send_email_stub(user_id=user_id, event_type=event_type, title=title, body=body)
        return notification

    async def resolve_team_id(self, organization_id: str, team_ref: str) -> str | None:
        """Resolve a team UUID or case-insensitive team name to a team id."""
        try:
            uuid.UUID(str(team_ref))
            team = await self.db.get(Team, team_ref)
            if team is not None and team.organization_id == organization_id:
                return team.id
        except (ValueError, AttributeError):
            pass
        team = await self.db.scalar(
            select(Team).where(Team.organization_id == organization_id, Team.name.ilike(str(team_ref)))
        )
        return team.id if team else None

    async def notify_team(
        self,
        *,
        team_id: str,
        organization_id: str,
        event_type: str,
        title: str,
        body: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        resolved_id = await self.resolve_team_id(organization_id, team_id)
        if resolved_id is None:
            return 0
        members = await self.db.execute(select(TeamMember.user_id).where(TeamMember.team_id == resolved_id))
        count = 0
        for (user_id,) in members.all():
            if await self.notify(
                user_id=user_id,
                organization_id=organization_id,
                event_type=event_type,
                title=title,
                body=body,
                metadata=metadata,
            ):
                count += 1
        return count

    async def notify_managers(
        self,
        *,
        organization_id: str,
        event_type: str,
        title: str,
        body: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        from app.infrastructure.database.models import Role

        result = await self.db.execute(
            select(User.id)
            .join(Role, User.role_id == Role.id)
            .where(User.organization_id == organization_id, Role.name.in_([RoleName.MANAGER, RoleName.ADMIN, RoleName.OWNER]))
        )
        count = 0
        for (user_id,) in result.all():
            if await self.notify(
                user_id=user_id,
                organization_id=organization_id,
                event_type=event_type,
                title=title,
                body=body,
                metadata=metadata,
            ):
                count += 1
        return count

    async def _get_preference(self, user_id: str, event_type: str) -> NotificationPreference | None:
        return await self.db.scalar(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id,
                NotificationPreference.event_type == event_type,
            )
        )

    async def ensure_default_preferences(self, user_id: str) -> None:
        for event_type in DEFAULT_EVENT_TYPES:
            existing = await self._get_preference(user_id, event_type)
            if existing is None:
                self.db.add(
                    NotificationPreference(
                        user_id=user_id,
                        event_type=event_type,
                        in_app=True,
                        email=False,
                        enabled=True,
                    )
                )
        await self.db.flush()

    def _send_email_stub(
        self,
        *,
        user_id: str,
        event_type: str,
        title: str,
        body: str,
    ) -> None:
        """Foundation hook for email delivery — logs until a real provider is wired."""
        logger.info(
            "email notification stub user=%s event=%s title=%s body=%s",
            user_id,
            event_type,
            title,
            body[:120],
        )
