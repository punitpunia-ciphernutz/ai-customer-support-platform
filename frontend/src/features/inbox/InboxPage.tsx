import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/services/api/client";
import { Link, useSearchParams } from "react-router-dom";
import type { ChannelType, Conversation, Customer, Message, UserListItem } from "@/types";
import { AgentAvailabilityControl } from "@/features/agents/AgentAvailabilityControl";
import { useAuth } from "@/features/auth/AuthContext";
import { AiRespondingIndicator, MessageBubble } from "@/features/conversations/MessageBubble";
import { useSupportSocket } from "@/hooks/useSupportSocket";
import { useInboxAwaitingAi } from "@/hooks/useAwaitingAiResponse";
import { Alert, Avatar, EmptyState, LoadingState } from "@/components/ui";
import { cn } from "@/utils/cn";
import { formatCost, statusClass } from "@/utils/format";
import type { AIUsageSummary } from "@/types";

type View = "all" | "mine" | "unassigned" | "team" | "web_chat" | "email";

const VIEW_LABELS: Record<View, string> = {
  all: "All",
  mine: "Mine",
  unassigned: "Unassigned",
  team: "Team",
  web_chat: "Web Chat",
  email: "Email",
};

const CHANNEL_BADGE: Record<ChannelType, string> = {
  WEB_CHAT: "Web Chat",
  EMAIL: "Email",
  FORM: "Form",
};

export function InboxPage() {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const deepLinkId = searchParams.get("c");
  const isOrgAdmin = user?.role.name === "OWNER" || user?.role.name === "ADMIN";
  const [view, setView] = useState<View>(isOrgAdmin ? "all" : "team");
  const [selectedId, setSelectedId] = useState<string | null>(deepLinkId);
  const [reply, setReply] = useState("");
  const [emailSubject, setEmailSubject] = useState("");
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

  const conversationAiUsage = useQuery({
    queryKey: ["conversation-ai-usage", selectedId],
    queryFn: () => api<AIUsageSummary>(`/conversations/${selectedId}/ai-usage`),
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
        if (selectedId) {
          void qc.invalidateQueries({ queryKey: ["messages", selectedId] });
          void qc.invalidateQueries({ queryKey: ["conversation-ai-usage", selectedId] });
        }
      }
    },
  });

  const selected = useMemo(
    () => conversations.data?.find((c) => c.id === selectedId) ?? null,
    [conversations.data, selectedId]
  );

  const { awaitingAi } = useInboxAwaitingAi(messages.data, selected?.ai_control_mode);

  const customerEmail = (id: string) =>
    customers.data?.find((c) => c.id === id)?.email ?? null;

  const customerName = (id: string) =>
    customers.data?.find((c) => c.id === id)?.name ?? "Customer";

  const latestAiMeta = useMemo(() => {
    const aiMsgs = (messages.data ?? []).filter(
      (m) => m.sender_type === "AI" && m.metadata && !m.metadata.internal
    );
    return aiMsgs.length ? aiMsgs[aiMsgs.length - 1].metadata : null;
  }, [messages.data]);

  const latestSuggestion = useMemo(() => {
    const list = messages.data ?? [];
    for (let i = list.length - 1; i >= 0; i--) {
      const m = list[i];
      if (m.metadata?.suggestion && m.metadata?.suggestion_status === "generated") {
        return m;
      }
    }
    return undefined;
  }, [messages.data]);

  const takeover = useMutation({
    mutationFn: () =>
      api<Conversation>(`/conversations/${selectedId}/takeover`, { method: "POST" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["conversations"] }),
  });

  const returnToAi = useMutation({
    mutationFn: () =>
      api<Conversation>(`/conversations/${selectedId}/return-to-ai`, { method: "POST" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["conversations"] }),
  });

  const rejectSuggestion = useMutation({
    mutationFn: (messageId: string) =>
      api<Message>(`/conversations/${selectedId}/suggestions/${messageId}/reject`, { method: "POST" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["messages", selectedId] }),
  });

  const regenerateSuggestion = useMutation({
    mutationFn: (messageId: string) =>
      api<Message>(`/conversations/${selectedId}/suggestions/${messageId}/regenerate`, { method: "POST" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["messages", selectedId] }),
  });

  const acceptSuggestion = useMutation({
    mutationFn: (messageId: string) =>
      api<Message>(`/conversations/${selectedId}/suggestions/${messageId}/accept`, { method: "POST" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["messages", selectedId] }),
  });

  const sendReply = useMutation({
    mutationFn: () => {
      if (selected?.channel === "EMAIL") {
        return api<Message>(`/conversations/${selectedId}/email`, {
          method: "POST",
          body: JSON.stringify({
            content: reply,
            subject: emailSubject || undefined,
          }),
        });
      }
      return api<Message>(`/conversations/${selectedId}/messages`, {
        method: "POST",
        body: JSON.stringify({ content: reply, sender_type: "AGENT" }),
      });
    },
    onSuccess: () => {
      setReply("");
      setEmailSubject("");
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
  }, [messages.data, awaitingAi]);

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
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <AgentAvailabilityControl />
          <div className="filter-pills">
          {(["team", "mine", "unassigned", "web_chat", "email", ...(isOrgAdmin ? (["all"] as View[]) : [])] as View[]).map((v) => (
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
                    <span className={statusClass("pending")}>{CHANNEL_BADGE[c.channel]}</span>
                    <span className={statusClass(c.status.toLowerCase())}>{c.status}</span>
                    {c.subject && <span>{c.subject}</span>}
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
                      <span className={statusClass("pending")}>{CHANNEL_BADGE[selected.channel]}</span>
                      {" · "}
                      {selected.subject ?? "No subject"}
                      {" · "}
                      <Link to={`/customers/${selected.customer_id}`}>Customer 360</Link>
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
                  {selected.ai_control_mode === "HUMAN_CONTROL" ? (
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => returnToAi.mutate()}
                      disabled={returnToAi.isPending}
                    >
                      Return to AI
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => takeover.mutate()}
                      disabled={takeover.isPending}
                    >
                      Takeover
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
                {(messages.data ?? [])
                  .filter((m) => !m.metadata?.internal)
                  .map((m) => (
                    <MessageBubble key={m.id} message={m} />
                  ))}
                {awaitingAi && <AiRespondingIndicator />}
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
                      {conversationAiUsage.data && (
                        <>
                          <div><dt>AI cost (conversation)</dt><dd>{formatCost(conversationAiUsage.data.total_cost_usd)}</dd></div>
                          <div><dt>AI runs</dt><dd>{conversationAiUsage.data.total_runs}</dd></div>
                          <div><dt>Tokens</dt><dd>{conversationAiUsage.data.total_tokens.total.toLocaleString()}</dd></div>
                        </>
                      )}
                    </dl>
                  )}
                </aside>
              )}

              {latestSuggestion && (
                <aside className="ai-panel" style={{ borderColor: "var(--accent)" }}>
                  <h3 className="section-title" style={{ fontSize: "0.875rem" }}>AI Suggested Reply</h3>
                  <p style={{ fontSize: "0.875rem", marginBottom: "0.5rem" }}>{latestSuggestion.content}</p>
                  <div className="form-hint mb-2">
                    Confidence: {latestSuggestion.metadata?.confidence != null
                      ? `${Math.round(latestSuggestion.metadata.confidence * 100)}%`
                      : "—"}
                    {latestSuggestion.metadata?.grounded === false && (
                      <span style={{ color: "var(--warning)", marginLeft: "0.5rem" }}>
                        · Not grounded
                      </span>
                    )}
                    {latestSuggestion.metadata?.citations?.length
                      ? ` · Source: ${latestSuggestion.metadata.citations.map((c) => c.title).join(", ")}`
                      : null}
                  </div>
                  <div className="flex gap-2" style={{ flexWrap: "wrap" }}>
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      onClick={() => {
                        setReply(latestSuggestion.content);
                        if (selected?.channel === "EMAIL") {
                          setEmailSubject(selected.subject ? `Re: ${selected.subject.replace(/^Re:\s*/i, "")}` : "Re: Support");
                        }
                        acceptSuggestion.mutate(latestSuggestion.id);
                      }}
                    >
                      Use Reply
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => setReply(latestSuggestion.content)}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => regenerateSuggestion.mutate(latestSuggestion.id)}
                      disabled={regenerateSuggestion.isPending}
                    >
                      Regenerate
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => rejectSuggestion.mutate(latestSuggestion.id)}
                      disabled={rejectSuggestion.isPending}
                    >
                      Ignore
                    </button>
                  </div>
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
                {selected.channel === "EMAIL" && (
                  <>
                    <input
                      className="form-input"
                      value={customerEmail(selected.customer_id) ?? ""}
                      readOnly
                      placeholder="To"
                      style={{ marginBottom: "0.5rem" }}
                      aria-label="To"
                    />
                    <input
                      className="form-input"
                      value={emailSubject}
                      onChange={(e) => setEmailSubject(e.target.value)}
                      placeholder={`Subject (Re: ${selected.subject ?? "Support"})`}
                      style={{ marginBottom: "0.5rem" }}
                    />
                  </>
                )}
                <input
                  className="form-input"
                  value={reply}
                  onChange={(e) => setReply(e.target.value)}
                  placeholder={selected.channel === "EMAIL" ? "Reply via email…" : "Reply to customer…"}
                />
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={!reply.trim() || sendReply.isPending}
                >
                  {selected.channel === "EMAIL" ? "Send Email" : "Reply"}
                </button>
              </form>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
