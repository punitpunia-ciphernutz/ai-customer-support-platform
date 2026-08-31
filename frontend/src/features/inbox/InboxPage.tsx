import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/services/api/client";
import { Link, useSearchParams } from "react-router-dom";
import type { Conversation, Customer, Message, UserListItem } from "@/types";
import { useAuth } from "@/features/auth/AuthContext";
import { useSupportSocket } from "@/hooks/useSupportSocket";
import { Alert, Avatar, EmptyState, LoadingState } from "@/components/ui";
import { cn } from "@/utils/cn";
import { statusClass } from "@/utils/format";

type View = "all" | "mine" | "unassigned" | "team";

const VIEW_LABELS: Record<View, string> = {
  all: "All",
  mine: "Mine",
  unassigned: "Unassigned",
  team: "Team",
};

export function InboxPage() {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const deepLinkId = searchParams.get("c");
  const [view, setView] = useState<View>("all");
  const [selectedId, setSelectedId] = useState<string | null>(deepLinkId);
  const [reply, setReply] = useState("");
  const [aiPanelOpen, setAiPanelOpen] = useState(true);
  const qc = useQueryClient();

  const conversations = useQuery({
    queryKey: ["conversations", view],
    queryFn: () => api<Conversation[]>(`/conversations?view=${view}`),
  });

  useEffect(() => {
    if (!deepLinkId) return;
    setView("all");
    setSelectedId(deepLinkId);
    const next = new URLSearchParams(searchParams);
    next.delete("c");
    setSearchParams(next, { replace: true });
  }, [deepLinkId]); // eslint-disable-line react-hooks/exhaustive-deps -- apply once per deep link

  const customers = useQuery({
    queryKey: ["customers"],
    queryFn: () => api<Customer[]>("/customers"),
  });

  const users = useQuery({
    queryKey: ["users"],
    queryFn: () => api<UserListItem[]>("/users"),
  });

  const teams = useQuery({
    queryKey: ["teams"],
    queryFn: () => api<{ id: string; name: string }[]>("/teams"),
  });

  const messages = useQuery({
    queryKey: ["messages", selectedId],
    queryFn: () => api<Message[]>(`/conversations/${selectedId}/messages`),
    enabled: !!selectedId,
  });

  useSupportSocket({
    token: localStorage.getItem("access_token"),
    onEvent: (event) => {
      if (
        event.name === "message.created" ||
        event.name?.startsWith("conversation.") ||
        event.name?.startsWith("ticket.")
      ) {
        void qc.invalidateQueries({ queryKey: ["conversations"] });
        void qc.invalidateQueries({ queryKey: ["tickets"] });
        if (selectedId) void qc.invalidateQueries({ queryKey: ["messages", selectedId] });
      }
    },
  });

  const selected = useMemo(
    () => conversations.data?.find((c) => c.id === selectedId) ?? null,
    [conversations.data, selectedId]
  );

  const customerName = (id: string) =>
    customers.data?.find((c) => c.id === id)?.name ?? "Customer";

  const senderLabel = (type: string) => (type === "AI" ? "AI Support" : type);

  const latestAiMeta = useMemo(() => {
    const aiMsgs = (messages.data ?? []).filter(
      (m) => m.sender_type === "AI" && m.metadata && !m.metadata.internal
    );
    return aiMsgs.length ? aiMsgs[aiMsgs.length - 1].metadata : null;
  }, [messages.data]);

  const sendReply = useMutation({
    mutationFn: () =>
      api<Message>(`/conversations/${selectedId}/messages`, {
        method: "POST",
        body: JSON.stringify({ content: reply, sender_type: "AGENT" }),
      }),
    onSuccess: () => {
      setReply("");
      void qc.invalidateQueries({ queryKey: ["messages", selectedId] });
      void qc.invalidateQueries({ queryKey: ["conversations"] });
    },
  });

  const patchConversation = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api<Conversation>(`/conversations/${selectedId}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["conversations"] });
    },
  });

  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.data]);

  return (
    <div className="page-full">
      <div
        style={{
          padding: "0.875rem 1.25rem",
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-card)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "1rem",
          flexWrap: "wrap",
        }}
      >
        <div>
          <h1 className="page-title" style={{ fontSize: "1.125rem" }}>Inbox</h1>
          <p className="page-desc" style={{ margin: 0, fontSize: "0.8125rem" }}>
            Manage conversations, assign agents, and reply to customers.
          </p>
        </div>
        <div className="filter-pills">
          {(["all", "mine", "unassigned", "team"] as View[]).map((v) => (
            <button
              key={v}
              type="button"
              className={cn("filter-pill", view === v && "active")}
              onClick={() => setView(v)}
            >
              {VIEW_LABELS[v]}
            </button>
          ))}
        </div>
      </div>

      <div className="split-layout">
        <section className="split-list">
          {conversations.isLoading && <LoadingState message="Loading conversations…" />}
          {conversations.isError && (
            <div style={{ padding: "1rem" }}>
              <Alert type="error">
                {conversations.error instanceof ApiError
                  ? conversations.error.message
                  : "Failed to load conversations."}
              </Alert>
            </div>
          )}
          {!conversations.isLoading && !conversations.data?.length && (
            <EmptyState message="No conversations yet. Create a customer and open Web Chat." />
          )}
          {conversations.data?.map((c) => (
            <button
              key={c.id}
              type="button"
              className={cn("list-item", selectedId === c.id && "selected")}
              onClick={() => setSelectedId(c.id)}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
                <Avatar name={customerName(c.customer_id)} size="sm" />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div className="list-item-title">{customerName(c.customer_id)}</div>
                  <div className="list-item-meta">
                    <span className={statusClass(c.status.toLowerCase())}>{c.status}</span>
                    <span className={statusClass(c.priority.toLowerCase())}>{c.priority}</span>
                  </div>
                </div>
              </div>
            </button>
          ))}
        </section>

        <section className="split-detail">
          {!selected && (
            <EmptyState message="Select a conversation to view messages and reply." />
          )}
          {selected && (
            <>
              <header className="thread-header">
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                  <Avatar name={customerName(selected.customer_id)} />
                  <div>
                    <h2 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>
                      {customerName(selected.customer_id)}
                    </h2>
                    <p className="text-sm text-muted" style={{ margin: "0.125rem 0 0" }}>
                      {selected.channel.replace(/_/g, " ")} · {selected.subject ?? "No subject"}
                    </p>
                  </div>
                </div>
                <div className="thread-actions">
                  <select
                    value={selected.status}
                    onChange={(e) => patchConversation.mutate({ status: e.target.value })}
                    aria-label="Status"
                  >
                    {["OPEN", "PENDING", "CLOSED"].map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                  <select
                    value={selected.priority}
                    onChange={(e) => patchConversation.mutate({ priority: e.target.value })}
                    aria-label="Priority"
                  >
                    {["LOW", "NORMAL", "HIGH", "URGENT"].map((p) => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                  </select>
                  <select
                    value={selected.assigned_user_id ?? ""}
                    onChange={(e) =>
                      patchConversation.mutate({ assigned_user_id: e.target.value || null })
                    }
                    aria-label="Assignee"
                  >
                    <option value="">Unassigned</option>
                    {(users.data ?? (user ? [user] : [])).map((u) => (
                      <option key={u.id} value={u.id}>{u.full_name}</option>
                    ))}
                  </select>
                  <select
                    value={selected.assigned_team_id ?? ""}
                    onChange={(e) =>
                      patchConversation.mutate({ assigned_team_id: e.target.value || null })
                    }
                    aria-label="Team"
                  >
                    <option value="">No team</option>
                    {(teams.data ?? []).map((t) => (
                      <option key={t.id} value={t.id}>{t.name}</option>
                    ))}
                  </select>
                  {selected.status !== "CLOSED" ? (
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => patchConversation.mutate({ status: "CLOSED" })}
                    >
                      Close
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => patchConversation.mutate({ status: "OPEN" })}
                    >
                      Reopen
                    </button>
                  )}
                </div>
              </header>

              <div className="messages-area">
                {messages.isLoading && <LoadingState message="Loading messages…" />}
                {messages.isError && (
                  <Alert type="error">
                    {messages.error instanceof ApiError
                      ? messages.error.message
                      : "Failed to load messages."}
                  </Alert>
                )}
                {messages.data?.map((m) => (
                  <div
                    key={m.id}
                    className={cn("message-bubble", m.sender_type.toLowerCase())}
                  >
                    <div className="message-sender">{senderLabel(m.sender_type)}</div>
                    <div>{m.content}</div>
                    {m.sender_type === "AI" && m.metadata?.confidence != null && (
                      <div className="message-ai-tag">
                        AI Response · {Math.round(m.metadata.confidence * 100)}%
                      </div>
                    )}
                  </div>
                ))}
                <div ref={bottomRef} />
              </div>

              {latestAiMeta && (
                <aside className="ai-panel">
                  <button
                    type="button"
                    className="ai-panel-toggle"
                    onClick={() => setAiPanelOpen((v) => !v)}
                  >
                    AI Information {aiPanelOpen ? "▾" : "▸"}
                  </button>
                  {aiPanelOpen && (
                    <dl>
                      <div><dt>Intent</dt><dd>{latestAiMeta.intent ?? "—"}</dd></div>
                      <div><dt>Confidence</dt><dd>{latestAiMeta.confidence != null ? `${Math.round(latestAiMeta.confidence * 100)}%` : "—"}</dd></div>
                      <div><dt>Knowledge</dt><dd>{latestAiMeta.citations?.map((c) => c.title).join(", ") || "—"}</dd></div>
                      <div><dt>Status</dt><dd>{latestAiMeta.ai_status ?? (latestAiMeta.grounded ? "Grounded" : "—")}</dd></div>
                    </dl>
                  )}
                </aside>
              )}

              <div style={{ padding: "0 1.25rem 0.5rem", fontSize: "0.8125rem" }}>
                <Link to="/settings">Configure AI in Settings →</Link>
              </div>

              <form
                className="composer"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (reply.trim()) sendReply.mutate();
                }}
              >
                <input
                  className="form-input"
                  value={reply}
                  onChange={(e) => setReply(e.target.value)}
                  placeholder="Reply to customer…"
                />
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={!reply.trim() || sendReply.isPending}
                >
                  Reply
                </button>
              </form>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
