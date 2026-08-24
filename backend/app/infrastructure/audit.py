from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import ActorType, AuditLog


async def write_audit(
    db: AsyncSession,
    *,
    organization_id: str,
    actor_type: ActorType,
    actor_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        organization_id=organization_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
        created_at=datetime.now(UTC),
    )
    db.add(entry)
    await db.flush()
    return entry
