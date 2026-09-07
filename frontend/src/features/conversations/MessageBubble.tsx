import { useState } from "react";
import type { Message, MessageAttachment } from "@/types";
import { API_BASE } from "@/services/api/client";
import { cn } from "@/utils/cn";
import { formatMessageTime } from "@/utils/format";

function senderLabel(type: string) {
  if (type === "AI") return "AI Support";
  return type;
}

async function downloadAttachment(att: MessageAttachment) {
  const token = localStorage.getItem("access_token");
  const res = await fetch(`${API_BASE}/attachments/${att.id}/download`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) {
    if (res.status === 401) throw new Error("Sign in to download");
    let detail = "Download failed";
    try {
      const body = (await res.json()) as { detail?: string };
      if (typeof body.detail === "string" && body.detail.trim()) detail = body.detail;
    } catch {
      /* ignore non-JSON errors */
    }
    throw new Error(detail);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = att.filename || "attachment";
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

function AttachmentLink({ att }: { att: MessageAttachment }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <span style={{ display: "inline-flex", flexDirection: "column", gap: "0.15rem" }}>
      <button
        type="button"
        className="btn btn-ghost btn-sm"
        disabled={busy}
        onClick={() => {
          setError(null);
          setBusy(true);
          void downloadAttachment(att)
            .catch((e) => setError(e instanceof Error ? e.message : "Download failed"))
            .finally(() => setBusy(false));
        }}
      >
        📎 {busy ? "Downloading…" : att.filename}
      </button>
      {error && (
        <span className="text-muted" style={{ fontSize: "0.75rem", color: "var(--danger, #b91c1c)" }}>
          {error}
        </span>
      )}
    </span>
  );
}

export function MessageBubble({
  message,
  showDiagnostics = true,
}: {
  message: Message;
  /** Agent inbox diagnostics (confidence, cost, delivery). Off for customer surfaces. */
  showDiagnostics?: boolean;
}) {
  const isSystem = message.sender_type === "SYSTEM";

  return (
    <div
      className={cn("message-bubble", message.sender_type.toLowerCase())}
    >
      <div className="message-header">
        <span className="message-sender">
          {senderLabel(message.sender_type)}
          {showDiagnostics && message.channel && message.sender_type === "CUSTOMER" && (
            <span className="text-muted" style={{ marginLeft: "0.35rem", fontWeight: 400 }}>
              · {message.channel.replace(/_/g, " ")}
            </span>
          )}
        </span>
        <time className="message-time" dateTime={message.created_at}>
          {formatMessageTime(message.created_at)}
        </time>
      </div>
      <div>{message.content}</div>
      {(message.attachments ?? []).length > 0 && (
        <div className="message-attachments" style={{ marginTop: "0.5rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          {message.attachments!.map((att) => (
            <AttachmentLink key={att.id} att={att} />
          ))}
        </div>
      )}
      {showDiagnostics && message.delivery_status && (
        <div className="message-ai-tag">Delivery: {message.delivery_status}</div>
      )}
      {showDiagnostics && message.sender_type === "AI" && message.metadata?.confidence != null && (
        <div className="message-ai-tag">
          AI Response · {Math.round(message.metadata.confidence * 100)}%
          {message.metadata.estimated_cost_usd != null && (
            <> · ${message.metadata.estimated_cost_usd.toFixed(4)}</>
          )}
        </div>
      )}
      {isSystem &&
        message.metadata?.ticket_id &&
        (message.metadata?.timeout_escalation || message.metadata?.ai_escalation_notice) && (
        <div className="message-ai-tag">Ticket #{message.metadata.ticket_id.slice(0, 8)}…</div>
      )}
    </div>
  );
}

export function AiRespondingIndicator() {
  return (
    <div className="ai-responding" role="status" aria-live="polite">
      <span className="ai-responding-dots" aria-hidden />
      AI is responding…
    </div>
  );
}
