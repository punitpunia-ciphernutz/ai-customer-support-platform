"""Action registry and handlers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    AIControlMode,
    Conversation,
    ConversationStatus,
    Priority,
    Ticket,
    TicketSource,
    TicketStatus,
)
from app.modules.assignment.application.service import AssignmentService
from app.modules.automation.application.context_builder import AutomationContext
from app.modules.automation.domain.enums import ActionType
from app.modules.notifications.application.service import NotificationService
from app.modules.sla.application.service import SLAService
from app.modules.tags.application.service import TagService

ActionHandler = Callable[[AsyncSession, AutomationContext, dict[str, Any]], Awaitable[dict[str, Any]]]


async def _assign_team(db: AsyncSession, ctx: AutomationContext, action: dict[str, Any]) -> dict[str, Any]:
    value = action.get("value") or action.get("config", {}).get("team")
    if not ctx.conversation_id or not value:
        return {"skipped": True, "reason": "missing conversation or team"}
    changed = await AssignmentService(db).assign_team_by_name(ctx.conversation_id, ctx.organization_id, str(value))
    return {"changed": changed, "team": value}


async def _assign_user(db: AsyncSession, ctx: AutomationContext, action: dict[str, Any]) -> dict[str, Any]:
    value = action.get("value") or action.get("config", {}).get("user_id")
    if not ctx.conversation_id or not value:
        return {"skipped": True}
    changed = await AssignmentService(db).assign_user(ctx.conversation_id, ctx.organization_id, str(value))
    return {"changed": changed, "user_id": value}


async def _assign_round_robin(db: AsyncSession, ctx: AutomationContext, action: dict[str, Any]) -> dict[str, Any]:
    value = action.get("value") or action.get("config", {}).get("team")
    if not ctx.conversation_id or not value:
        return {"skipped": True}
    agent_id = await AssignmentService(db).assign_round_robin(ctx.conversation_id, ctx.organization_id, str(value))
    return {"agent_id": agent_id, "team": value}


async def _set_priority(db: AsyncSession, ctx: AutomationContext, action: dict[str, Any]) -> dict[str, Any]:
    value = str(action.get("value") or action.get("config", {}).get("priority", "NORMAL")).upper()
    if not ctx.conversation_id:
        return {"skipped": True}
    conv = await db.get(Conversation, ctx.conversation_id)
    if conv is None:
        return {"skipped": True}
    new_priority = Priority(value)
    if conv.priority == new_priority:
        return {"changed": False, "priority": value}
    conv.priority = new_priority
    await db.flush()
    await SLAService(db).start_timers_for_conversation(ctx.organization_id, ctx.conversation_id, new_priority)
    ctx.priority = value
    return {"changed": True, "priority": value}


async def _set_status(db: AsyncSession, ctx: AutomationContext, action: dict[str, Any]) -> dict[str, Any]:
    value = str(action.get("value") or action.get("config", {}).get("status", "OPEN")).upper()
    if not ctx.conversation_id:
        return {"skipped": True}
    conv = await db.get(Conversation, ctx.conversation_id)
    if conv is None:
        return {"skipped": True}
    new_status = ConversationStatus(value)
    if conv.status == new_status:
        return {"changed": False, "status": value}
    conv.status = new_status
    await db.flush()
    return {"changed": True, "status": value}


async def _add_tag(db: AsyncSession, ctx: AutomationContext, action: dict[str, Any]) -> dict[str, Any]:
    value = action.get("value") or action.get("config", {}).get("tag")
    if not ctx.conversation_id or not value:
        return {"skipped": True}
    changed = await TagService(db).add_conversation_tag(ctx.organization_id, ctx.conversation_id, str(value))
    return {"changed": changed, "tag": value}


async def _remove_tag(db: AsyncSession, ctx: AutomationContext, action: dict[str, Any]) -> dict[str, Any]:
    value = action.get("value") or action.get("config", {}).get("tag")
    if not ctx.conversation_id or not value:
        return {"skipped": True}
    changed = await TagService(db).remove_conversation_tag(ctx.organization_id, ctx.conversation_id, str(value))
    return {"changed": changed, "tag": value}


async def _create_ticket(db: AsyncSession, ctx: AutomationContext, action: dict[str, Any]) -> dict[str, Any]:
    idempotency = action.get("config", {}).get("idempotency_key")
    if idempotency and ctx.metadata.get("ticket_created_for", {}).get(idempotency):
        return {"skipped": True, "reason": "idempotent"}
    title = action.get("config", {}).get("title") or "Automation ticket"
    if ctx.conversation_id:
        existing = await db.scalar(
            select(Ticket).where(
                Ticket.conversation_id == ctx.conversation_id,
                Ticket.source.in_(
                    [
                        TicketSource.AUTOMATION,
                        TicketSource.MISSED_CHAT,
                        TicketSource.AI_ESCALATION,
                    ]
                ),
            )
        )
        if existing:
            ctx.ticket_id = existing.id
            return {"skipped": True, "ticket_id": existing.id}
    ticket = Ticket(
        organization_id=ctx.organization_id,
        customer_id=ctx.customer_id,
        conversation_id=ctx.conversation_id,
        title=title,
        description=action.get("config", {}).get("description") or "Created by automation",
        source=TicketSource.MISSED_CHAT if ctx.metadata.get("event") == "missed_chat" else TicketSource.AUTOMATION,
        status=TicketStatus.OPEN,
        priority=Priority(ctx.priority) if ctx.priority else Priority.NORMAL,
        assigned_team_id=ctx.assigned_team_id,
    )
    db.add(ticket)
    await db.flush()
    ctx.ticket_id = ticket.id
    if idempotency:
        created = dict(ctx.metadata.get("ticket_created_for") or {})
        created[idempotency] = ticket.id
        ctx.metadata["ticket_created_for"] = created
    return {"changed": True, "ticket_id": ticket.id}


async def _assign_ticket(db: AsyncSession, ctx: AutomationContext, action: dict[str, Any]) -> dict[str, Any]:
    ticket_id = ctx.ticket_id or action.get("config", {}).get("ticket_id")
    if not ticket_id:
        return {"skipped": True, "reason": "missing ticket"}
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None or ticket.organization_id != ctx.organization_id:
        return {"skipped": True}
    team = action.get("value") or action.get("config", {}).get("team")
    user_id = action.get("config", {}).get("user_id")
    changed = False
    if team:
        team_id = await NotificationService(db).resolve_team_id(ctx.organization_id, str(team))
        if team_id and ticket.assigned_team_id != team_id:
            ticket.assigned_team_id = team_id
            changed = True
    if user_id and ticket.assigned_user_id != user_id:
        ticket.assigned_user_id = str(user_id)
        changed = True
    if changed:
        await db.flush()
    return {"changed": changed, "ticket_id": ticket_id}


async def _set_ticket_priority(db: AsyncSession, ctx: AutomationContext, action: dict[str, Any]) -> dict[str, Any]:
    ticket_id = ctx.ticket_id or action.get("config", {}).get("ticket_id")
    value = str(action.get("value") or action.get("config", {}).get("priority", "NORMAL")).upper()
    if not ticket_id:
        return {"skipped": True}
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None:
        return {"skipped": True}
    new_priority = Priority(value)
    if ticket.priority == new_priority:
        return {"changed": False}
    ticket.priority = new_priority
    await db.flush()
    return {"changed": True, "priority": value}


async def _enable_ai(db: AsyncSession, ctx: AutomationContext, action: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    if not ctx.conversation_id:
        return {"skipped": True}
    conv = await db.get(Conversation, ctx.conversation_id)
    if conv is None:
        return {"skipped": True}
    if conv.ai_control_mode == AIControlMode.AI_CONTROL:
        return {"changed": False}
    conv.ai_control_mode = AIControlMode.AI_CONTROL
    await db.flush()
    return {"changed": True}


async def _disable_ai(db: AsyncSession, ctx: AutomationContext, action: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    if not ctx.conversation_id:
        return {"skipped": True}
    conv = await db.get(Conversation, ctx.conversation_id)
    if conv is None:
        return {"skipped": True}
    if conv.ai_control_mode == AIControlMode.HUMAN_CONTROL:
        return {"changed": False}
    conv.ai_control_mode = AIControlMode.HUMAN_CONTROL
    await db.flush()
    return {"changed": True}


async def _escalate_to_human(db: AsyncSession, ctx: AutomationContext, action: dict[str, Any]) -> dict[str, Any]:
    result = await _disable_ai(db, ctx, action)
    if result.get("skipped"):
        return result
    team = action.get("value") or action.get("config", {}).get("team")
    if team and ctx.conversation_id:
        await AssignmentService(db).assign_team_by_name(ctx.conversation_id, ctx.organization_id, str(team))
    return {"changed": True, **result}


async def _notify_agent(db: AsyncSession, ctx: AutomationContext, action: dict[str, Any]) -> dict[str, Any]:
    user_id = action.get("value") or action.get("config", {}).get("user_id") or ctx.assigned_user_id
    if not user_id:
        return {"skipped": True}
    notification = await NotificationService(db).notify(
        user_id=str(user_id),
        organization_id=ctx.organization_id,
        event_type="AUTOMATION_NOTIFY",
        title=action.get("config", {}).get("title") or "Automation notification",
        body=action.get("config", {}).get("body") or f"Automation triggered for conversation {ctx.conversation_id}",
        metadata={"conversation_id": ctx.conversation_id},
    )
    return {"notified": 1 if notification else 0}


async def _notify_team(db: AsyncSession, ctx: AutomationContext, action: dict[str, Any]) -> dict[str, Any]:
    team_ref = action.get("value") or action.get("config", {}).get("team") or ctx.assigned_team_id or "Support"
    count = await NotificationService(db).notify_team(
        team_id=str(team_ref),
        organization_id=ctx.organization_id,
        event_type="AUTOMATION_NOTIFY",
        title=action.get("config", {}).get("title") or "Automation notification",
        body=action.get("config", {}).get("body") or f"Automation triggered for conversation {ctx.conversation_id}",
        metadata={"conversation_id": ctx.conversation_id},
    )
    return {"notified": count}


async def _notify_manager(db: AsyncSession, ctx: AutomationContext, action: dict[str, Any]) -> dict[str, Any]:
    count = await NotificationService(db).notify_managers(
        organization_id=ctx.organization_id,
        event_type="MANAGER_ALERT",
        title=action.get("config", {}).get("title") or "Manager alert",
        body=action.get("config", {}).get("body") or f"Automation alert for conversation {ctx.conversation_id}",
        metadata={"conversation_id": ctx.conversation_id, "intent": ctx.intent, "sentiment": ctx.sentiment},
    )
    return {"notified": count}


ACTION_REGISTRY: dict[ActionType, ActionHandler] = {
    ActionType.ASSIGN_TEAM: _assign_team,
    ActionType.ASSIGN_USER: _assign_user,
    ActionType.ASSIGN_ROUND_ROBIN: _assign_round_robin,
    ActionType.SET_PRIORITY: _set_priority,
    ActionType.SET_STATUS: _set_status,
    ActionType.ADD_TAG: _add_tag,
    ActionType.REMOVE_TAG: _remove_tag,
    ActionType.CREATE_TICKET: _create_ticket,
    ActionType.ASSIGN_TICKET: _assign_ticket,
    ActionType.SET_TICKET_PRIORITY: _set_ticket_priority,
    ActionType.ENABLE_AI: _enable_ai,
    ActionType.DISABLE_AI: _disable_ai,
    ActionType.ESCALATE_TO_HUMAN: _escalate_to_human,
    ActionType.NOTIFY_AGENT: _notify_agent,
    ActionType.NOTIFY_TEAM: _notify_team,
    ActionType.NOTIFY_MANAGER: _notify_manager,
}


async def execute_action(db: AsyncSession, ctx: AutomationContext, action: dict[str, Any]) -> dict[str, Any]:
    action_type = ActionType(action.get("type"))
    handler = ACTION_REGISTRY.get(action_type)
    if handler is None:
        return {"skipped": True, "reason": f"unsupported action {action_type}"}
    return await handler(db, ctx, action)
