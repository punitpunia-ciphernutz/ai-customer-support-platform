import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/services/api/client";
import type { Message } from "@/types";
import { findPendingCustomerMessage } from "@/features/conversations/chatUtils";

type AIResponseStatus = {
  status: "pending" | "responded" | "ticket_created";
  ticket_id: string | null;
  timeout_seconds: number;
};

const DEFAULT_TIMEOUT_SECONDS = 60;

export function useAwaitingAiResponse({
  messages,
  conversationId,
  customerId,
  enabled = true,
  onTicketCreated,
  onMessagesRefresh,
}: {
  messages: Message[];
  conversationId: string;
  customerId: string;
  enabled?: boolean;
  onTicketCreated?: (ticketId: string) => void;
  onMessagesRefresh?: () => void;
}) {
  const [sending, setSending] = useState(false);
  const [timeoutSeconds, setTimeoutSeconds] = useState(DEFAULT_TIMEOUT_SECONDS);
  const [ticketId, setTicketId] = useState<string | null>(null);
  const checkedRef = useRef<Set<string>>(new Set());

  const pendingMessage = useMemo(() => {
    if (!enabled) return null;
    return findPendingCustomerMessage(messages);
  }, [messages, enabled]);

  const awaitingAi = pendingMessage !== null && !sending;

  useEffect(() => {
    if (!pendingMessage || !conversationId || !customerId) return undefined;

    const elapsed = Date.now() - new Date(pendingMessage.created_at).getTime();
    const remaining = Math.max(0, timeoutSeconds * 1000 - elapsed);

    const timer = window.setTimeout(() => {
      const key = `${conversationId}:${pendingMessage.id}`;
      if (checkedRef.current.has(key)) return;
      checkedRef.current.add(key);

      void (async () => {
        try {
          const result = await api<AIResponseStatus>(
            `/public/conversations/${conversationId}/check-ai-response`,
            {
              method: "POST",
              auth: false,
              body: JSON.stringify({
                customer_id: customerId,
                message_id: pendingMessage.id,
              }),
            }
          );
          setTimeoutSeconds(result.timeout_seconds);
          if (result.status === "ticket_created" && result.ticket_id) {
            setTicketId(result.ticket_id);
            onTicketCreated?.(result.ticket_id);
            onMessagesRefresh?.();
          }
        } catch {
          // Beat task may still create the ticket server-side.
        }
      })();
    }, remaining);

    return () => window.clearTimeout(timer);
  }, [
    pendingMessage,
    conversationId,
    customerId,
    timeoutSeconds,
    onTicketCreated,
    onMessagesRefresh,
  ]);

  useEffect(() => {
    if (!pendingMessage) {
      setTicketId(null);
    }
  }, [pendingMessage]);

  return {
    sending,
    setSending,
    awaitingAi,
    pendingMessage,
    timeoutSeconds,
    ticketId,
  };
}

export function useInboxAwaitingAi(messages: Message[] | undefined, aiControlMode?: string) {
  const pendingMessage = useMemo(() => {
    if (!messages || aiControlMode === "HUMAN_CONTROL") return null;
    return findPendingCustomerMessage(messages);
  }, [messages, aiControlMode]);

  return {
    awaitingAi: pendingMessage !== null,
    pendingMessage,
  };
}
