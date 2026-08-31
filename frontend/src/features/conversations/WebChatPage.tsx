import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/services/api/client";
import type { Conversation, Message } from "@/types";
import { useSupportSocket } from "@/hooks/useSupportSocket";
import { Alert } from "@/components/ui";
import { IconSupport } from "@/components/ui/icons";
import { cn } from "@/utils/cn";

function senderLabel(type: string) {
  if (type === "AI") return "AI Support";
  return type;
}

function isCustomerVisible(m: Message) {
  return !m.metadata?.internal;
}

export function WebChatPage() {
  const [customerId, setCustomerId] = useState(
    () => localStorage.getItem("chat_customer_id") ?? ""
  );
  const [conversationId, setConversationId] = useState(
    () => localStorage.getItem("chat_conversation_id") ?? ""
  );
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const loadMessages = async (cid: string, custId: string) => {
    const list = await api<Message[]>(
      `/public/conversations/${cid}/messages?customer_id=${encodeURIComponent(custId)}`,
      { auth: false }
    );
    setMessages(list);
  };

  useEffect(() => {
    if (conversationId && customerId) {
      setLoading(true);
      void loadMessages(conversationId, customerId)
        .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
        .finally(() => setLoading(false));
    }
  }, [conversationId, customerId]);

  useSupportSocket({
    token: null,
    publicSocket: true,
    onEvent: (event) => {
      if (event.name === "message.created" && conversationId) {
        void loadMessages(conversationId, customerId);
      }
    },
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const startOrSend = async () => {
    setError(null);
    if (!customerId.trim() || !text.trim()) return;
    localStorage.setItem("chat_customer_id", customerId);
    try {
      let cid = conversationId;
      if (!cid) {
        const conv = await api<Conversation>("/public/conversations", {
          method: "POST",
          auth: false,
          body: JSON.stringify({
            customer_id: customerId,
            channel: "WEB_CHAT",
            initial_message: text,
          }),
        });
        cid = conv.id;
        setConversationId(cid);
        localStorage.setItem("chat_conversation_id", cid);
        setText("");
        await loadMessages(cid, customerId);
        return;
      }
      await api(`/public/conversations/${cid}/messages`, {
        method: "POST",
        auth: false,
        body: JSON.stringify({ content: text, customer_id: customerId }),
      });
      setText("");
      await loadMessages(cid, customerId);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Send failed");
    }
  };

  return (
    <div className="chat-page">
      <header className="chat-header">
        <h1>
          <IconSupport size={22} />
          Web Chat
        </h1>
        <p className="page-desc" style={{ margin: "0.375rem 0 0" }}>
          Paste a customer ID from the agent Customers page, then send a message.
        </p>
      </header>

      <div className="form-field">
        <label className="form-label" htmlFor="customer-id">Customer ID</label>
        <input
          id="customer-id"
          className="form-input"
          value={customerId}
          onChange={(e) => setCustomerId(e.target.value)}
          placeholder="UUID from Customers page"
        />
      </div>

      <div className="chat-thread">
        {loading && (
          <p className="text-muted text-sm" style={{ textAlign: "center" }}>Loading messages…</p>
        )}
        {!loading && !messages.filter(isCustomerVisible).length && (
          <p className="text-muted text-sm" style={{ textAlign: "center", margin: "auto" }}>
            Send a message to start the conversation.
          </p>
        )}
        {messages.filter(isCustomerVisible).map((m) => (
          <div key={m.id} className={cn("message-bubble", m.sender_type.toLowerCase())}>
            <div className="message-sender">{senderLabel(m.sender_type)}</div>
            {m.content}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {error && <Alert type="error">{error}</Alert>}

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void startOrSend();
        }}
      >
        <input
          className="form-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Hello, I need help…"
        />
        <button type="submit" className="btn btn-primary" disabled={!text.trim() || !customerId.trim()}>
          Send
        </button>
      </form>

      <button
        type="button"
        className="btn btn-ghost btn-sm"
        style={{ alignSelf: "center" }}
        onClick={() => {
          setConversationId("");
          localStorage.removeItem("chat_conversation_id");
          setMessages([]);
        }}
      >
        Start new conversation
      </button>
    </div>
  );
}
