import { useEffect, useRef, useState } from "react";
import { api } from "@/services/api/client";
import type { Conversation, Message } from "@/types";
import { useSupportSocket } from "@/hooks/useSupportSocket";

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
      void loadMessages(conversationId, customerId).catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load")
      );
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
      setError(e instanceof Error ? e.message : "Send failed");
    }
  };

  return (
    <div className="chat">
      <header>
        <h1>Web Chat</h1>
        <p>Paste a customer ID from the agent Customers page, then send a message.</p>
      </header>
      <label>
        Customer ID
        <input
          value={customerId}
          onChange={(e) => setCustomerId(e.target.value)}
          placeholder="UUID from Customers"
        />
      </label>
      <div className="thread">
        {messages.filter(isCustomerVisible).map((m) => (
          <div key={m.id} className={`bubble ${m.sender_type.toLowerCase()}`}>
            <div className="meta">{senderLabel(m.sender_type)}</div>
            {m.content}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      {error && <p className="error">{error}</p>}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void startOrSend();
        }}
      >
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Hello, I need help."
        />
        <button type="submit">Send</button>
      </form>
      <button
        type="button"
        className="reset"
        onClick={() => {
          setConversationId("");
          localStorage.removeItem("chat_conversation_id");
          setMessages([]);
        }}
      >
        Start new conversation
      </button>
      <style>{`
        .chat {
          max-width: 560px; margin: 0 auto; min-height: 100%;
          padding: 1.5rem; display: flex; flex-direction: column; gap: 0.75rem;
        }
        h1 { font-family: var(--font-display); margin: 0; color: var(--accent); font-weight: 400; }
        header p { color: var(--text-muted); margin: 0.35rem 0 0; }
        label { display: grid; gap: 0.35rem; font-size: 0.85rem; color: var(--text-muted); }
        input, button {
          background: var(--bg-elevated); border: 1px solid var(--border); color: var(--text);
          border-radius: 8px; padding: 0.65rem 0.75rem;
        }
        .thread {
          flex: 1; min-height: 280px; background: var(--bg-elevated);
          border: 1px solid var(--border); border-radius: 12px; padding: 1rem;
          display: grid; gap: 0.65rem; align-content: start; overflow: auto;
        }
        .bubble { max-width: 80%; padding: 0.65rem 0.8rem; border-radius: 12px; background: var(--bg-panel); }
        .bubble.customer { margin-left: auto; background: #1f3d34; }
        .bubble.ai { margin-right: auto; border: 1px solid #2d6a5a; background: #152a24; }
        .bubble.agent { margin-right: auto; }
        .meta { font-size: 0.7rem; color: var(--text-muted); }
        form { display: flex; gap: 0.5rem; }
        form input { flex: 1; }
        form button, .reset {
          background: var(--accent); color: #06140f; border: none; font-weight: 600; cursor: pointer;
        }
        .reset { background: transparent; color: var(--text-muted); border: 1px solid var(--border); }
        .error { color: var(--danger); margin: 0; }
      `}</style>
    </div>
  );
}
