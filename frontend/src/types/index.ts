export type Role = { id: string; name: string; permissions: string[] };
export type User = {
  id: string;
  organization_id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  role: Role;
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
  channel: string;
  status: string;
  priority: string;
  assigned_user_id: string | null;
  assigned_team_id: string | null;
  subject: string | null;
  created_at: string;
  updated_at: string;
};

export type Message = {
  id: string;
  conversation_id: string;
  sender_type: string;
  sender_id: string | null;
  content: string;
  created_at: string;
  metadata?: {
    ai_run_id?: string;
    confidence?: number;
    intent?: string;
    grounded?: boolean;
    citations?: { document_id: string; title: string }[];
    ai_status?: string;
    internal?: boolean;
    ai_escalation?: boolean;
  };
};

export type AIConfig = {
  enabled: boolean;
  mode: "DRAFT_ONLY" | "SUGGEST" | "AUTO_REPLY";
  auto_reply_threshold: number;
  escalation_threshold: number;
};
