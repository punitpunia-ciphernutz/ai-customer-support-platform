"""Automation engine enums."""

from enum import StrEnum


class AutomationTriggerType(StrEnum):
    CONVERSATION_CREATED = "CONVERSATION_CREATED"
    CONVERSATION_UPDATED = "CONVERSATION_UPDATED"
    CONVERSATION_ASSIGNED = "CONVERSATION_ASSIGNED"
    CONVERSATION_REOPENED = "CONVERSATION_REOPENED"
    CONVERSATION_CLOSED = "CONVERSATION_CLOSED"
    MESSAGE_RECEIVED = "MESSAGE_RECEIVED"
    MESSAGE_SENT = "MESSAGE_SENT"
    TICKET_CREATED = "TICKET_CREATED"
    TICKET_UPDATED = "TICKET_UPDATED"
    TICKET_ASSIGNED = "TICKET_ASSIGNED"
    TICKET_RESOLVED = "TICKET_RESOLVED"
    TICKET_REOPENED = "TICKET_REOPENED"
    AI_ESCALATED = "AI_ESCALATED"
    AI_RESOLVED = "AI_RESOLVED"
    AI_LOW_CONFIDENCE = "AI_LOW_CONFIDENCE"
    CUSTOMER_CREATED = "CUSTOMER_CREATED"
    CUSTOMER_UPDATED = "CUSTOMER_UPDATED"
    MISSED_CHAT = "MISSED_CHAT"


class ConditionOperator(StrEnum):
    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    CONTAINS = "CONTAINS"
    NOT_CONTAINS = "NOT_CONTAINS"
    STARTS_WITH = "STARTS_WITH"
    ENDS_WITH = "ENDS_WITH"
    IN = "IN"
    NOT_IN = "NOT_IN"
    GREATER_THAN = "GREATER_THAN"
    LESS_THAN = "LESS_THAN"
    GREATER_OR_EQUAL = "GREATER_OR_EQUAL"
    LESS_OR_EQUAL = "LESS_OR_EQUAL"
    IS_EMPTY = "IS_EMPTY"
    IS_NOT_EMPTY = "IS_NOT_EMPTY"


class ActionType(StrEnum):
    ASSIGN_TEAM = "ASSIGN_TEAM"
    ASSIGN_USER = "ASSIGN_USER"
    ASSIGN_ROUND_ROBIN = "ASSIGN_ROUND_ROBIN"
    SET_PRIORITY = "SET_PRIORITY"
    SET_STATUS = "SET_STATUS"
    ADD_TAG = "ADD_TAG"
    REMOVE_TAG = "REMOVE_TAG"
    CREATE_TICKET = "CREATE_TICKET"
    ASSIGN_TICKET = "ASSIGN_TICKET"
    SET_TICKET_PRIORITY = "SET_TICKET_PRIORITY"
    ENABLE_AI = "ENABLE_AI"
    DISABLE_AI = "DISABLE_AI"
    ESCALATE_TO_HUMAN = "ESCALATE_TO_HUMAN"
    NOTIFY_AGENT = "NOTIFY_AGENT"
    NOTIFY_TEAM = "NOTIFY_TEAM"
    NOTIFY_MANAGER = "NOTIFY_MANAGER"


class ExecutionStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class StepType(StrEnum):
    CONDITION = "CONDITION"
    ACTION = "ACTION"


# Map domain event names to automation trigger types
EVENT_TO_TRIGGER: dict[str, AutomationTriggerType] = {
    "conversation.created": AutomationTriggerType.CONVERSATION_CREATED,
    "conversation.updated": AutomationTriggerType.CONVERSATION_UPDATED,
    "conversation.assigned": AutomationTriggerType.CONVERSATION_ASSIGNED,
    "conversation.reopened": AutomationTriggerType.CONVERSATION_REOPENED,
    "conversation.closed": AutomationTriggerType.CONVERSATION_CLOSED,
    "message.received": AutomationTriggerType.MESSAGE_RECEIVED,
    "message.sent": AutomationTriggerType.MESSAGE_SENT,
    "ticket.created": AutomationTriggerType.TICKET_CREATED,
    "ticket.updated": AutomationTriggerType.TICKET_UPDATED,
    "ticket.assigned": AutomationTriggerType.TICKET_ASSIGNED,
    "ticket.resolved": AutomationTriggerType.TICKET_RESOLVED,
    "ticket.reopened": AutomationTriggerType.TICKET_REOPENED,
    "ai.escalated": AutomationTriggerType.AI_ESCALATED,
    "ai.resolved": AutomationTriggerType.AI_RESOLVED,
    "ai.low_confidence": AutomationTriggerType.AI_LOW_CONFIDENCE,
    "customer.created": AutomationTriggerType.CUSTOMER_CREATED,
    "customer.updated": AutomationTriggerType.CUSTOMER_UPDATED,
    "missed_chat": AutomationTriggerType.MISSED_CHAT,
}
