import type { Message } from "@/types";

export function findPendingCustomerMessage(messages: Message[]): Message | null {
  const visible = messages.filter((m) => !m.metadata?.internal);
  for (let i = visible.length - 1; i >= 0; i -= 1) {
    const msg = visible[i];
    if (msg.sender_type !== "CUSTOMER") continue;
    if (msg.metadata?.timeout_ticket_id) return null;

    const hasResponse = visible.slice(i + 1).some(
      (m) =>
        m.sender_type === "AGENT" ||
        m.sender_type === "AI" ||
        (m.sender_type === "SYSTEM" &&
          (m.metadata?.offline_notice || m.metadata?.timeout_escalation))
    );
    if (!hasResponse) return msg;
    break;
  }
  return null;
}
