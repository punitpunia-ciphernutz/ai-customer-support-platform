import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Conversation, Message } from "@/types";
import { AiRespondingIndicator, MessageBubble } from "@/features/conversations/MessageBubble";
import { findPendingCustomerMessage } from "@/features/conversations/chatUtils";
import { useSupportSocket } from "@/hooks/useSupportSocket";
import {
  clearVisitorState,
  isVisitorAuthError,
  loadVisitorState,
  saveVisitorState,
  widgetApi,
  WidgetApiError,
} from "@/widget/api";
import type { PublicWidgetConfig, WidgetSession } from "@/widget/types";

function isCustomerVisible(m: Message) {
  return !m.metadata?.internal;
}

function params() {
  const q = new URLSearchParams(window.location.search);
  return {
    widgetId: q.get("widget_id") ?? "",
    pageHost: q.get("page_host") ?? "localhost",
    previewToken: q.get("preview_token"),
  };
}

export function WidgetFrameApp() {
  const { widgetId, pageHost: initialHost, previewToken } = useMemo(() => params(), []);
  const [pageHost, setPageHost] = useState(initialHost);
  const [pageUrl, setPageUrl] = useState<string | undefined>();
  const [config, setConfig] = useState<PublicWidgetConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [session, setSession] = useState<WidgetSession | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [prechatDone, setPrechatDone] = useState(false);
  const [sending, setSending] = useState(false);
  const [ticketNotice, setTicketNotice] = useState<string | null>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const checkedRef = useRef<Set<string>>(new Set());
  const sessionRef = useRef<WidgetSession | null>(null);
  const sessionRefreshRef = useRef<Promise<WidgetSession> | null>(null);

  sessionRef.current = session;

  const primary = config?.appearance?.primary_color ?? "#3B66F5";
  const textColor = config?.appearance?.text_color ?? "#FFFFFF";
  const radius = config?.appearance?.border_radius_px ?? 16;

  useEffect(() => {
    window.parent.postMessage({ type: "WIDGET_READY", widgetId }, "*");
    const onMessage = (event: MessageEvent) => {
      const data = event.data || {};
      if (data.type === "WIDGET_INIT" && data.host) {
        setPageHost(String(data.host));
        if (data.href) setPageUrl(String(data.href));
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [widgetId]);

  useEffect(() => {
    if (!config?.appearance) return;
    window.parent.postMessage(
      { type: "WIDGET_APPEARANCE", widgetId, appearance: config.appearance },
      "*"
    );
  }, [config, widgetId]);

  useEffect(() => {
    if (!widgetId) {
      setError("Missing widget id");
      setLoading(false);
      return;
    }
    void (async () => {
      try {
        const cfg = await widgetApi<PublicWidgetConfig>(`/public/widgets/${widgetId}/config`, {
          pageHost,
          previewToken,
        });
        setConfig(cfg);
        const stored = loadVisitorState(widgetId);
        if (stored?.visitor_token) {
          setSession({
            visitor_key: stored.visitor_key,
            customer_id: stored.customer_id,
            visitor_token: stored.visitor_token,
            expires_at: "",
            conversation_id: stored.conversation_id ?? null,
          });
          if (stored.conversation_id) setConversationId(stored.conversation_id);
          setPrechatDone(true);
        } else if (!cfg.require_email && !cfg.require_name) {
          setPrechatDone(true);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load widget");
      } finally {
        setLoading(false);
      }
    })();
  }, [widgetId, pageHost, previewToken]);

  const ensureSession = useCallback(
    async (opts?: { force?: boolean }) => {
      if (!opts?.force && sessionRef.current?.visitor_token) {
        return sessionRef.current;
      }

      if (opts?.force && sessionRefreshRef.current) {
        return sessionRefreshRef.current;
      }

      const create = async (): Promise<WidgetSession> => {
        const current = sessionRef.current;
        const stored = loadVisitorState(widgetId);
        // Prefer in-memory key; storage may still hold visitor_key after a token wipe.
        const visitorKey = current?.visitor_key || stored?.visitor_key;

        if (opts?.force) {
          clearVisitorState(widgetId);
          setSession(null);
          sessionRef.current = null;
        }

        const body = {
          visitor_key: visitorKey,
          name: name || undefined,
          email: email || undefined,
          page_host: pageHost,
          page_url: pageUrl,
        };
        const next = await widgetApi<WidgetSession>(`/public/widgets/${widgetId}/session`, {
          method: "POST",
          pageHost,
          previewToken,
          body: JSON.stringify(body),
        });
        saveVisitorState(widgetId, {
          visitor_key: next.visitor_key,
          visitor_token: next.visitor_token,
          customer_id: next.customer_id,
          conversation_id: next.conversation_id,
        });
        sessionRef.current = next;
        setSession(next);
        if (next.conversation_id) setConversationId(next.conversation_id);
        return next;
      };

      if (opts?.force) {
        const pending = create().finally(() => {
          sessionRefreshRef.current = null;
        });
        sessionRefreshRef.current = pending;
        return pending;
      }

      return create();
    },
    [widgetId, name, email, pageHost, pageUrl, previewToken]
  );

  /** Run an authenticated widget call; on visitor 401, refresh session once and retry. */
  const withVisitorAuth = useCallback(
    async <T,>(operation: (sess: WidgetSession) => Promise<T>): Promise<T> => {
      try {
        const sess = await ensureSession();
        return await operation(sess);
      } catch (e) {
        if (!isVisitorAuthError(e)) throw e;
        clearVisitorState(widgetId);
        setSession(null);
        sessionRef.current = null;
        setError(null);
        const sess = await ensureSession({ force: true });
        return await operation(sess);
      }
    },
    [ensureSession, widgetId]
  );

  const applyMessages = useCallback((list: Message[]) => {
    setMessages((prev) => {
      if (
        prev.length === list.length &&
        prev.every(
          (m, i) =>
            m.id === list[i]?.id &&
            m.content === list[i]?.content &&
            m.created_at === list[i]?.created_at
        )
      ) {
        return prev;
      }
      return list;
    });
  }, []);

  const loadMessages = useCallback(
    async (cid: string, token: string) => {
      const list = await widgetApi<Message[]>(
        `/public/widgets/${widgetId}/conversations/${cid}/messages`,
        { pageHost, visitorToken: token, previewToken, publicId: widgetId }
      );
      applyMessages(list);
    },
    [widgetId, pageHost, previewToken, applyMessages]
  );

  const loadMessagesWithRecovery = useCallback(
    async (cid: string) => {
      await withVisitorAuth(async (sess) => {
        const targetId = sess.conversation_id || cid;
        if (targetId !== cid) setConversationId(targetId);
        await loadMessages(targetId, sess.visitor_token);
      });
    },
    [withVisitorAuth, loadMessages]
  );

  useEffect(() => {
    if (conversationId && session?.visitor_token) {
      void loadMessagesWithRecovery(conversationId).catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load messages")
      );
    }
  }, [conversationId, session?.visitor_token, loadMessagesWithRecovery]);

  // Poll so AI replies appear without a full page refresh if WS is delayed.
  useEffect(() => {
    if (!conversationId || !session?.visitor_token) return undefined;
    const id = window.setInterval(() => {
      void loadMessagesWithRecovery(conversationId).catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(id);
  }, [conversationId, session?.visitor_token, loadMessagesWithRecovery]);

  useSupportSocket({
    token: session?.visitor_token ?? null,
    publicSocket: true,
    conversationId,
    onEvent: (event) => {
      if (
        (event.name === "message.created" || event.name === "message.received") &&
        conversationId &&
        session?.visitor_token
      ) {
        void loadMessagesWithRecovery(conversationId);
      }
    },
  });

  const visibleMessages = messages.filter(isCustomerVisible);
  const pending = findPendingCustomerMessage(messages);
  const awaitingAi = pending !== null && !sending;

  useEffect(() => {
    if (!pending || !conversationId || !session?.visitor_token) return undefined;
    const elapsed = Date.now() - new Date(pending.created_at).getTime();
    const remaining = Math.max(0, 60000 - elapsed);
    const timer = window.setTimeout(() => {
      const key = `${conversationId}:${pending.id}`;
      if (checkedRef.current.has(key)) return;
      checkedRef.current.add(key);
      void withVisitorAuth(async (sess) => {
        const result = await widgetApi<{ status?: string; ticket_id?: string | null }>(
          `/public/widgets/${widgetId}/conversations/${conversationId}/check-ai-response`,
          {
            method: "POST",
            pageHost,
            visitorToken: sess.visitor_token,
            publicId: widgetId,
            body: JSON.stringify({ message_id: pending.id }),
          }
        );
        if (result.status === "ticket_created" && result.ticket_id) {
          setTicketNotice(
            `A support ticket was created (${result.ticket_id.slice(0, 8)}…). Our team will follow up soon.`
          );
          await loadMessages(conversationId, sess.visitor_token);
        }
      }).catch(() => undefined);
    }, remaining);
    return () => window.clearTimeout(timer);
  }, [pending, conversationId, session, widgetId, pageHost, withVisitorAuth, loadMessages]);

  const onMessagesScroll = () => {
    const el = messagesRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickToBottomRef.current = distanceFromBottom <= 80;
  };

  useEffect(() => {
    const el = messagesRef.current;
    if (!el || !stickToBottomRef.current) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages, awaitingAi, sending]);

  const startPrechat = async () => {
    setError(null);
    try {
      if (config?.require_name && !name.trim()) {
        setError("Name is required");
        return;
      }
      if (config?.require_email && !email.trim()) {
        setError("Email is required");
        return;
      }
      await ensureSession();
      setPrechatDone(true);
    } catch (e) {
      setError(e instanceof WidgetApiError ? e.message : "Could not start session");
    }
  };

  const send = async () => {
    if (!text.trim() || !config) return;
    if (config.status !== "ACTIVE" && !previewToken) return;
    stickToBottomRef.current = true;
    setError(null);
    setTicketNotice(null);
    setSending(true);
    try {
      await withVisitorAuth(async (sess) => {
        const activeConversationId = conversationId ?? sess.conversation_id;
        if (!activeConversationId) {
          const conv = await widgetApi<Conversation>(`/public/widgets/${widgetId}/conversations`, {
            method: "POST",
            pageHost,
            visitorToken: sess.visitor_token,
            previewToken,
            publicId: widgetId,
            body: JSON.stringify({
              content: text.trim(),
              metadata: { page_url: pageUrl, page_host: pageHost },
            }),
          });
          setConversationId(conv.id);
          saveVisitorState(widgetId, {
            visitor_key: sess.visitor_key,
            visitor_token: sess.visitor_token,
            customer_id: sess.customer_id,
            conversation_id: conv.id,
          });
          setText("");
          await loadMessages(conv.id, sess.visitor_token);
          return;
        }

        await widgetApi(`/public/widgets/${widgetId}/conversations/${activeConversationId}/messages`, {
          method: "POST",
          pageHost,
          visitorToken: sess.visitor_token,
          previewToken,
          publicId: widgetId,
          body: JSON.stringify({
            content: text.trim(),
            metadata: { page_url: pageUrl, page_host: pageHost },
          }),
        });
        setText("");
        await loadMessages(activeConversationId, sess.visitor_token);
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to send");
    } finally {
      setSending(false);
    }
  };

  if (loading) {
    return (
      <div className="widget-frame" style={{ "--widget-primary": primary } as React.CSSProperties}>
        <div className="widget-frame-loading">Loading chat…</div>
      </div>
    );
  }

  if (error && !config) {
    return (
      <div className="widget-frame">
        <div className="widget-frame-error">{error}</div>
      </div>
    );
  }

  const offline = config?.status === "INACTIVE" && !previewToken;

  return (
    <div
      className="widget-frame"
      style={
        {
          "--widget-primary": primary,
          "--widget-text": textColor,
          "--widget-radius": `${radius}px`,
        } as React.CSSProperties
      }
    >
      <header className="widget-frame-header">
        <div>
          <strong>{config?.name ?? "Support"}</strong>
          <div className="widget-frame-sub">We typically reply in a few minutes</div>
        </div>
        <button
          type="button"
          className="widget-frame-close"
          onClick={() => window.parent.postMessage({ type: "WIDGET_CLOSE", widgetId }, "*")}
          aria-label="Close"
        >
          ×
        </button>
      </header>

      {offline ? (
        <div className="widget-frame-offline">
          {config?.offline_message || "We're offline right now. Please try again later."}
        </div>
      ) : !prechatDone ? (
        <div className="widget-frame-prechat">
          <p>{config?.welcome_message}</p>
          {config?.require_name && (
            <label>
              Name
              <input value={name} onChange={(e) => setName(e.target.value)} />
            </label>
          )}
          {config?.require_email && (
            <label>
              Email
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
          )}
          {error && <div className="widget-frame-inline-error">{error}</div>}
          <button type="button" className="widget-frame-send" onClick={() => void startPrechat()}>
            Start chat
          </button>
        </div>
      ) : (
        <>
          <div className="widget-frame-messages" ref={messagesRef} onScroll={onMessagesScroll}>
            {config?.welcome_message && visibleMessages.length === 0 && (
              <div className="widget-welcome">{config.welcome_message}</div>
            )}
            {ticketNotice && <div className="widget-ticket-notice">{ticketNotice}</div>}
            {error && <div className="widget-frame-inline-error">{error}</div>}
            {visibleMessages.map((m) => (
              <MessageBubble key={m.id} message={m} showDiagnostics={false} />
            ))}
            {(awaitingAi || sending) && <AiRespondingIndicator />}
          </div>
          <form
            className="widget-frame-composer"
            onSubmit={(e) => {
              e.preventDefault();
              void send();
            }}
          >
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Type your message…"
              disabled={sending}
              autoComplete="off"
            />
            <button type="submit" className="widget-frame-send" disabled={sending || !text.trim()}>
              Send
            </button>
          </form>
        </>
      )}
    </div>
  );
}
