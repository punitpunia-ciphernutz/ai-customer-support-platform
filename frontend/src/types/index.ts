// Enums — must match backend exactly
export type RoleName = "OWNER" | "ADMIN" | "MANAGER" | "AGENT" | "READ_ONLY";
export type ChannelType = "WEB_CHAT" | "EMAIL" | "FORM";
export type ConversationStatus = "OPEN" | "PENDING" | "WAITING_FOR_AGENT" | "CLOSED";
export type AIControlMode = "AI_CONTROL" | "HUMAN_CONTROL";
export type Priority = "LOW" | "NORMAL" | "HIGH" | "URGENT";
export type DeliveryStatus = "QUEUED" | "SENDING" | "SENT" | "DELIVERED" | "OPENED" | "FAILED";
export type SenderType = "CUSTOMER" | "AGENT" | "AI" | "SYSTEM";
export type MessageAttachment = {
  id: string;
  message_id: string | null;
  filename: string;
  mime_type: string;
  size: number;
  download_url?: string | null;
};
export type TicketStatus = "OPEN" | "IN_PROGRESS" | "WAITING" | "RESOLVED" | "CLOSED";
export type AIMode = "DRAFT_ONLY" | "SUGGEST" | "AUTO_REPLY";
export type IntentLabel =
  | "GENERAL_QUESTION"
  | "ACCOUNT_ACCESS"
  | "BILLING"
  | "TECHNICAL_ISSUE"
  | "BUG_REPORT"
  | "FEATURE_REQUEST"
  | "REFUND"
  | "CANCELLATION"
  | "OTHER";
export type AIRunType = "CLASSIFICATION" | "GENERATION" | "SUMMARY" | "RETRIEVAL" | "AGENT";
export type AIRunStatus = "PENDING" | "RUNNING" | "SUCCEEDED" | "COMPLETED" | "FAILED";
export type AgentDecision = "AI_RESOLVE" | "ESCALATE" | "SUGGEST_ONLY";

export type Role = { id: string; name: RoleName; permissions: string[] };

export type User = {
  id: string;
  organization_id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  role: Role;
  created_at: string;
};

export type UserListItem = {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
};

export type Team = {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  created_at: string;
};

export type Customer = {
  id: string;
  organization_id: string;
  name: string;
  email: string | null;
  phone: string | null;
  company_name: string | null;
  created_at: string;
};

export type Conversation = {
  id: string;
  organization_id: string;
  customer_id: string;
  channel: ChannelType;
  status: ConversationStatus;
  priority: Priority;
  assigned_user_id: string | null;
  assigned_team_id: string | null;
  subject: string | null;
  ai_control_mode?: AIControlMode;
  created_at: string;
  updated_at: string;
};

export type Message = {
  id: string;
  conversation_id: string;
  sender_type: SenderType;
  sender_id: string | null;
  content: string;
  channel?: ChannelType;
  external_message_id?: string | null;
  delivery_status?: DeliveryStatus | null;
  created_at: string;
  updated_at?: string;
  attachments?: MessageAttachment[];
  metadata?: {
    ai_run_id?: string;
    trigger_message_id?: string;
    confidence?: number;
    intent?: string;
    grounded?: boolean;
    citations?: { document_id: string; title: string; chunk_id?: string }[];
    ai_status?: string;
    internal?: boolean;
    ai_escalation?: boolean;
    escalation?: boolean;
    ticket_id?: string;
    timeout_ticket_id?: string;
    timeout_escalation?: boolean;
    offline_notice?: boolean;
    estimated_cost_usd?: number;
    suggestion?: boolean;
    suggestion_status?: string;
  };
};

export type Ticket = {
  id: string;
  organization_id: string;
  conversation_id: string;
  status: TicketStatus;
  priority: Priority;
  assigned_user_id: string | null;
  assigned_team_id: string | null;
  created_at: string;
  resolved_at: string | null;
  closed_at: string | null;
};

export type AIConfig = {
  enabled: boolean;
  mode: AIMode;
  mode_display?: string;
  auto_reply_threshold: number;
  escalation_threshold: number;
  min_relevance_score?: number;
  require_knowledge?: boolean;
  escalate_if_unknown?: boolean;
  multilingual_enabled?: boolean;
  missed_chat_timeout_minutes?: number;
  ai_response_timeout_seconds?: number;
  allowed_intents: string[] | null;
  restricted_intents: string[] | null;
  intent_team_map: Record<string, string> | null;
  channel_overrides?: { channel: string; mode: AIMode | null }[];
};

export type AIRunSummary = {
  id: string;
  conversation_id: string | null;
  message_id: string | null;
  type: AIRunType;
  status: AIRunStatus;
  model: string | null;
  graph_version: string | null;
  intent: string | null;
  retrieval_count: number | null;
  confidence: number | null;
  grounding_score?: number | null;
  decision?: string | null;
  estimated_cost_usd?: number | null;
  latency_ms: number | null;
  error: string | null;
  created_at: string;
};

export type AIRunDetail = AIRunSummary & {
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  token_usage: Record<string, unknown> | null;
  confidence_components?: Record<string, unknown> | null;
  trace?: Record<string, unknown>[] | null;
};

export type AIUsageSummary = {
  conversation_id?: string | null;
  period_days?: number | null;
  total_runs: number;
  total_cost_usd: number;
  total_tokens: { input: number; output: number; total: number };
};

export type AITestResponse = {
  intent: IntentLabel;
  confidence: number;
  grounded: boolean;
  answer: string;
  sources: { document_id: string; title: string; chunk_id?: string }[];
  escalation_required: boolean;
  escalation_reason: string | null;
  decision: AgentDecision;
};

export const INTENT_LABELS: IntentLabel[] = [
  "GENERAL_QUESTION",
  "ACCOUNT_ACCESS",
  "BILLING",
  "TECHNICAL_ISSUE",
  "BUG_REPORT",
  "FEATURE_REQUEST",
  "REFUND",
  "CANCELLATION",
  "OTHER",
];

export const TICKET_STATUSES: TicketStatus[] = [
  "OPEN",
  "IN_PROGRESS",
  "WAITING",
  "RESOLVED",
  "CLOSED",
];

export const PRIORITIES: Priority[] = ["LOW", "NORMAL", "HIGH", "URGENT"];
