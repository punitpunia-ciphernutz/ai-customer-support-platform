import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/services/api/client";
import type { Conversation, Customer, Message, User } from "@/types";
import { useAuth } from "@/features/auth/AuthContext";
import { useSupportSocket } from "@/hooks/useSupportSocket";

type View = "all" | "mine" | "unassigned" | "team";

export function InboxPage() {
  const { user } = useAuth();
  const [view, setView] = useState<View>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reply, setReply] = useState("");
  const qc = useQueryClient();

  const conversations = useQuery({
    queryKey: ["conversations", view],
    queryFn: () => api<Conversation[]>(`/conversations?view=${view}`),
  });

  const customers = useQuery({
    queryKey: ["customers"],
    queryFn: () => api<Customer[]>("/customers"),
  });

  const users = useQuery({
    queryKey: ["users"],
    queryFn: () => api<User[]>("/users"),
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
      if (event.name === "message.created" || event.name?.startsWith("conversation.")) {
        void qc.invalidateQueries({ queryKey: ["conversations"] });
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
    <div className="inbox">
      <div className="filters">
        {(["all", "mine", "unassigned", "team"] as View[]).map((v) => (
          <button
            key={v}
            type="button"
            className={view === v ? "active" : ""}
            onClick={() => setView(v)}
          >
            {v}
          </button>
        ))}
      </div>
      <div className="panes">
        <section className="list">
          <h2>Conversations</h2>
          {conversations.isLoading && <p className="muted">Loading…</p>}
          {conversations.data?.map((c) => (
            <button
              key={c.id}
              type="button"
              className={`item ${selectedId === c.id ? "selected" : ""}`}
              onClick={() => setSelectedId(c.id)}
            >
              <strong>{customerName(c.customer_id)}</strong>
              <span>
                {c.status} · {c.priority}
              </span>
            </button>
          ))}
          {!conversations.data?.length && !conversations.isLoading && (
            <p className="muted">No conversations yet. Create a customer and open Web Chat.</p>
          )}
        </section>
        <section className="thread">
          {!selected && <div className="empty">Select a conversation</div>}
          {selected && (
            <>
              <header>
                <div>
                  <h2>{customerName(selected.customer_id)}</h2>
                  <p className="muted">
                    {selected.channel} · {selected.status} · {selected.priority}
                  </p>
                </div>
                <div className="actions">
                  <select
                    value={selected.status}
                    onChange={(e) => patchConversation.mutate({ status: e.target.value })}
                    aria-label="Status"
                  >
                    {["OPEN", "PENDING", "CLOSED"].map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                  <select
                    value={selected.priority}
                    onChange={(e) => patchConversation.mutate({ priority: e.target.value })}
                    aria-label="Priority"
                  >
                    {["LOW", "NORMAL", "HIGH", "URGENT"].map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                  <select
                    value={selected.assigned_user_id ?? ""}
                    onChange={(e) =>
                      patchConversation.mutate({
                        assigned_user_id: e.target.value || null,
                      })
                    }
                    aria-label="Assignee"
                  >
                    <option value="">Unassigned</option>
                    {(users.data ?? (user ? [user] : [])).map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.full_name}
                      </option>
                    ))}
                  </select>
                  <select
                    value={selected.assigned_team_id ?? ""}
                    onChange={(e) =>
                      patchConversation.mutate({
                        assigned_team_id: e.target.value || null,
                      })
                    }
                    aria-label="Team"
                  >
                    <option value="">No team</option>
                    {(teams.data ?? []).map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                  {selected.status !== "CLOSED" ? (
                    <button
                      type="button"
                      onClick={() => patchConversation.mutate({ status: "CLOSED" })}
                    >
                      Close
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => patchConversation.mutate({ status: "OPEN" })}
                    >
                      Reopen
                    </button>
                  )}
                </div>
              </header>
              <div className="messages">
                {messages.data?.map((m) => (
                  <div key={m.id} className={`bubble ${m.sender_type.toLowerCase()}`}>
                    <div className="meta">{m.sender_type}</div>
                    <div>{m.content}</div>
                  </div>
                ))}
                <div ref={bottomRef} />
              </div>
              <form
                className="composer"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (reply.trim()) sendReply.mutate();
                }}
              >
                <input
                  value={reply}
                  onChange={(e) => setReply(e.target.value)}
                  placeholder="Reply to customer…"
                />
                <button type="submit" disabled={!reply.trim() || sendReply.isPending}>
                  Reply
                </button>
              </form>
            </>
          )}
        </section>
      </div>
      <style>{`
        .inbox { height: 100%; display: flex; flex-direction: column; }
        .filters {
          display: flex; gap: 0.5rem; padding: 0.75rem 1rem;
          border-bottom: 1px solid var(--border);
        }
        .filters button {
          background: transparent; border: 1px solid var(--border); color: var(--text-muted);
          border-radius: 999px; padding: 0.35rem 0.85rem; cursor: pointer; text-transform: capitalize;
        }
        .filters button.active { background: var(--accent); color: #06140f; border-color: transparent; }
        .panes { flex: 1; display: grid; grid-template-columns: 320px 1fr; min-height: 0; }
        .list, .thread { min-height: 0; overflow: auto; }
        .list { border-right: 1px solid var(--border); padding: 1rem; }
        .list h2, .thread h2 { margin: 0 0 0.75rem; font-size: 1rem; }
        .item {
          width: 100%; text-align: left; background: transparent; border: 1px solid transparent;
          color: var(--text); border-radius: 10px; padding: 0.75rem; cursor: pointer;
          display: grid; gap: 0.2rem; margin-bottom: 0.35rem;
        }
        .item span { color: var(--text-muted); font-size: 0.8rem; }
        .item.selected, .item:hover { background: var(--bg-panel); border-color: var(--border); }
        .thread { display: flex; flex-direction: column; }
        .thread header {
          display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap;
          padding: 1rem; border-bottom: 1px solid var(--border);
        }
        .actions { display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; }
        .actions select, .actions button, .composer button, .composer input {
          background: var(--bg); border: 1px solid var(--border); color: var(--text);
          border-radius: 8px; padding: 0.45rem 0.65rem;
        }
        .actions button, .composer button {
          background: var(--accent); color: #06140f; border: none; cursor: pointer; font-weight: 600;
        }
        .messages { flex: 1; overflow: auto; padding: 1rem; display: grid; gap: 0.75rem; align-content: start; }
        .bubble {
          max-width: 70%; padding: 0.75rem 0.9rem; border-radius: 12px; background: var(--bg-panel);
        }
        .bubble.agent { margin-left: auto; background: #1f3d34; }
        .bubble.customer { margin-right: auto; }
        .meta { font-size: 0.7rem; color: var(--text-muted); margin-bottom: 0.25rem; }
        .composer { display: flex; gap: 0.5rem; padding: 1rem; border-top: 1px solid var(--border); }
        .composer input { flex: 1; }
        .empty, .muted { color: var(--text-muted); padding: 2rem; }
        @media (max-width: 900px) {
          .panes { grid-template-columns: 1fr; }
        }
      `}</style>
    </div>
  );
}
