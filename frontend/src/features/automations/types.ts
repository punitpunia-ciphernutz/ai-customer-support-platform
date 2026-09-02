import type { ChannelType, ConversationStatus, IntentLabel, Priority } from "@/types";

export type AutomationTriggerType =
  | "CONVERSATION_CREATED"
  | "CONVERSATION_UPDATED"
  | "CONVERSATION_ASSIGNED"
  | "CONVERSATION_REOPENED"
  | "CONVERSATION_CLOSED"
  | "MESSAGE_RECEIVED"
  | "MESSAGE_SENT"
  | "TICKET_CREATED"
  | "TICKET_UPDATED"
  | "TICKET_ASSIGNED"
  | "TICKET_RESOLVED"
  | "TICKET_REOPENED"
  | "AI_ESCALATED"
  | "AI_RESOLVED"
  | "AI_LOW_CONFIDENCE"
  | "CUSTOMER_CREATED"
  | "CUSTOMER_UPDATED"
  | "MISSED_CHAT";

export type ConditionOperator =
  | "EQUALS"
  | "NOT_EQUALS"
  | "CONTAINS"
  | "NOT_CONTAINS"
  | "STARTS_WITH"
  | "ENDS_WITH"
  | "IN"
  | "NOT_IN"
  | "GREATER_THAN"
  | "LESS_THAN"
  | "GREATER_OR_EQUAL"
  | "LESS_OR_EQUAL"
  | "IS_EMPTY"
  | "IS_NOT_EMPTY";

export type ActionType =
  | "ASSIGN_TEAM"
  | "ASSIGN_USER"
  | "ASSIGN_ROUND_ROBIN"
  | "SET_PRIORITY"
  | "SET_STATUS"
  | "ADD_TAG"
  | "REMOVE_TAG"
  | "CREATE_TICKET"
  | "ASSIGN_TICKET"
  | "SET_TICKET_PRIORITY"
  | "ENABLE_AI"
  | "DISABLE_AI"
  | "ESCALATE_TO_HUMAN"
  | "NOTIFY_AGENT"
  | "NOTIFY_TEAM"
  | "NOTIFY_MANAGER";

export type ConditionLeaf = {
  field: string;
  operator: ConditionOperator;
  value?: string | number | string[];
};

export type ConditionGroup = {
  logic: "AND" | "OR";
  conditions: ConditionLeaf[];
};

export type ActionFormState = {
  id: string;
  type: ActionType;
  value?: string;
  config?: Record<string, unknown>;
};

export type ConditionFieldValueType = "intent" | "sentiment" | "channel" | "priority" | "status" | "text" | "number";

export type ConditionFieldDef = {
  id: string;
  label: string;
  valueType: ConditionFieldValueType;
  operators: ConditionOperator[];
};

export const AUTOMATION_TRIGGERS: AutomationTriggerType[] = [
  "MESSAGE_RECEIVED",
  "MESSAGE_SENT",
  "CONVERSATION_CREATED",
  "CONVERSATION_UPDATED",
  "CONVERSATION_ASSIGNED",
  "CONVERSATION_REOPENED",
  "CONVERSATION_CLOSED",
  "TICKET_CREATED",
  "TICKET_UPDATED",
  "TICKET_ASSIGNED",
  "TICKET_RESOLVED",
  "TICKET_REOPENED",
  "AI_ESCALATED",
  "AI_RESOLVED",
  "AI_LOW_CONFIDENCE",
  "CUSTOMER_CREATED",
  "CUSTOMER_UPDATED",
  "MISSED_CHAT",
];

export const AUTOMATION_ACTIONS: ActionType[] = [
  "ASSIGN_TEAM",
  "ASSIGN_USER",
  "ASSIGN_ROUND_ROBIN",
  "SET_PRIORITY",
  "SET_STATUS",
  "ADD_TAG",
  "REMOVE_TAG",
  "CREATE_TICKET",
  "ASSIGN_TICKET",
  "SET_TICKET_PRIORITY",
  "ENABLE_AI",
  "DISABLE_AI",
  "ESCALATE_TO_HUMAN",
  "NOTIFY_TEAM",
  "NOTIFY_MANAGER",
  "NOTIFY_AGENT",
];

export const CONDITION_OPERATORS: ConditionOperator[] = [
  "EQUALS",
  "NOT_EQUALS",
  "CONTAINS",
  "NOT_CONTAINS",
  "STARTS_WITH",
  "ENDS_WITH",
  "IN",
  "NOT_IN",
  "GREATER_THAN",
  "LESS_THAN",
  "GREATER_OR_EQUAL",
  "LESS_OR_EQUAL",
  "IS_EMPTY",
  "IS_NOT_EMPTY",
];

export const SENTIMENT_VALUES = ["POSITIVE", "NEUTRAL", "NEGATIVE", "ANGRY"] as const;

export const CONVERSATION_STATUSES: ConversationStatus[] = ["OPEN", "PENDING", "WAITING_FOR_AGENT", "CLOSED"];

export const CHANNEL_TYPES: ChannelType[] = ["WEB_CHAT", "EMAIL", "FORM"];

export const CONDITION_FIELDS: ConditionFieldDef[] = [
  {
    id: "intent",
    label: "Intent",
    valueType: "intent",
    operators: ["EQUALS", "NOT_EQUALS", "IN", "NOT_IN"],
  },
  {
    id: "sentiment",
    label: "Sentiment",
    valueType: "sentiment",
    operators: ["EQUALS", "NOT_EQUALS", "IN", "NOT_IN"],
  },
  {
    id: "channel",
    label: "Channel",
    valueType: "channel",
    operators: ["EQUALS", "NOT_EQUALS", "IN", "NOT_IN"],
  },
  {
    id: "priority",
    label: "Priority",
    valueType: "priority",
    operators: ["EQUALS", "NOT_EQUALS", "IN", "NOT_IN", "GREATER_THAN", "LESS_THAN", "GREATER_OR_EQUAL", "LESS_OR_EQUAL"],
  },
  {
    id: "status",
    label: "Status",
    valueType: "status",
    operators: ["EQUALS", "NOT_EQUALS", "IN", "NOT_IN"],
  },
  {
    id: "conversation.status",
    label: "Conversation status",
    valueType: "status",
    operators: ["EQUALS", "NOT_EQUALS", "IN", "NOT_IN"],
  },
  {
    id: "conversation.priority",
    label: "Conversation priority",
    valueType: "priority",
    operators: ["EQUALS", "NOT_EQUALS", "IN", "NOT_IN"],
  },
  {
    id: "tags",
    label: "Tags",
    valueType: "text",
    operators: ["CONTAINS", "NOT_CONTAINS", "IN", "NOT_IN", "IS_EMPTY", "IS_NOT_EMPTY"],
  },
  {
    id: "ai_confidence",
    label: "AI confidence",
    valueType: "number",
    operators: ["EQUALS", "NOT_EQUALS", "GREATER_THAN", "LESS_THAN", "GREATER_OR_EQUAL", "LESS_OR_EQUAL"],
  },
];

export const VALUELESS_OPERATORS: ConditionOperator[] = ["IS_EMPTY", "IS_NOT_EMPTY"];

export const MULTI_VALUE_OPERATORS: ConditionOperator[] = ["IN", "NOT_IN"];

export const ACTIONS_WITHOUT_VALUE: ActionType[] = [
  "NOTIFY_MANAGER",
  "ENABLE_AI",
  "DISABLE_AI",
  "ESCALATE_TO_HUMAN",
];

export const TEAM_ACTIONS: ActionType[] = ["ASSIGN_TEAM", "ASSIGN_ROUND_ROBIN", "NOTIFY_TEAM"];

export const USER_ACTIONS: ActionType[] = ["ASSIGN_USER", "NOTIFY_AGENT"];

export const PRIORITY_ACTIONS: ActionType[] = ["SET_PRIORITY", "SET_TICKET_PRIORITY"];

export function formatEnumLabel(value: string): string {
  return value
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function getDefaultCondition(): ConditionLeaf {
  return { field: "intent", operator: "EQUALS", value: "BILLING" };
}

export function getDefaultAction(): ActionFormState {
  return { id: crypto.randomUUID(), type: "SET_PRIORITY", value: "HIGH" };
}

export function getFieldDef(fieldId: string): ConditionFieldDef {
  return CONDITION_FIELDS.find((f) => f.id === fieldId) ?? CONDITION_FIELDS[0];
}

export function operatorNeedsValue(operator: ConditionOperator): boolean {
  return !VALUELESS_OPERATORS.includes(operator);
}

export function actionNeedsValue(type: ActionType): boolean {
  return !ACTIONS_WITHOUT_VALUE.includes(type);
}

export function actionUsesConfig(type: ActionType): boolean {
  return type === "CREATE_TICKET";
}

export type IntentOption = IntentLabel;
export type PriorityOption = Priority;
