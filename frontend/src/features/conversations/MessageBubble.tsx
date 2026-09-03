import type { Message } from "@/types";
import { cn } from "@/utils/cn";
import { formatMessageTime } from "@/utils/format";

function senderLabel(type: string) {
  if (type === "AI") return "AI Support";
  return type;
}

export function MessageBubble({ message }: { message: Message }) {
  const isSystem = message.sender_type === "SYSTEM";

  return (
    <div
      className={cn("message-bubble", message.sender_type.toLowerCase())}
    >
      <div className="message-header">
        <span className="message-sender">
          {senderLabel(message.sender_type)}
          {message.channel && message.sender_type === "CUSTOMER" && (
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
            <a
              key={att.id}
              className="btn btn-ghost btn-sm"
              href={att.download_url ?? `#attachment-${att.id}`}
              target="_blank"
              rel="noreferrer"
            >
              📎 {att.filename}
            </a>
          ))}
        </div>
      )}
      {message.delivery_status && (
        <div className="message-ai-tag">Delivery: {message.delivery_status}</div>
      )}
      {message.sender_type === "AI" && message.metadata?.confidence != null && (
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
