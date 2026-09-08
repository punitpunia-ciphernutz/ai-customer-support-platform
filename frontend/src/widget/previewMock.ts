import type { Message } from "@/types";

export const PREVIEW_SAMPLE_USER = "Hi, I have a question.";
export const PREVIEW_SAMPLE_REPLY = "Sure, how can I help you today?";

const PREVIEW_CONVERSATION_ID = "preview-conversation";

/** Static sample thread for Settings Live Preview — never persisted. */
export function buildPreviewMessages(welcomeMessage: string): Message[] {
  const now = Date.now();
  const welcome = welcomeMessage.trim() || "Hi! How can we help?";
  return [
    {
      id: "preview-welcome",
      conversation_id: PREVIEW_CONVERSATION_ID,
      sender_type: "AI",
      sender_id: null,
      content: welcome,
      created_at: new Date(now - 120_000).toISOString(),
    },
    {
      id: "preview-user",
      conversation_id: PREVIEW_CONVERSATION_ID,
      sender_type: "CUSTOMER",
      sender_id: null,
      content: PREVIEW_SAMPLE_USER,
      created_at: new Date(now - 60_000).toISOString(),
    },
    {
      id: "preview-reply",
      conversation_id: PREVIEW_CONVERSATION_ID,
      sender_type: "AI",
      sender_id: null,
      content: PREVIEW_SAMPLE_REPLY,
      created_at: new Date(now - 30_000).toISOString(),
    },
  ];
}

export type WidgetPreviewDraft = {
  name?: string;
  welcome_message?: string;
  appearance?: {
    primary_color?: string;
    text_color?: string;
    launcher_position?: string;
    launcher_text?: string;
    border_radius_px?: number;
  };
};

export const WIDGET_PREVIEW_UPDATE = "WIDGET_PREVIEW_UPDATE" as const;
