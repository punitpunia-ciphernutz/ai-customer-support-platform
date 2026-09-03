import { useMemo, useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/services/api/client";
import { formatDate, formatRelative, statusClass } from "@/utils/format";
import type {
  Conversation,
  Customer,
  Priority,
  Ticket,
  TicketStatus,
  UserListItem,
} from "@/types";
import { PRIORITIES, TICKET_STATUSES } from "@/types";
import { useSupportSocket } from "@/hooks/useSupportSocket";
import {
  Alert,
  Avatar,
  EmptyState,
  LoadingState,
  Modal,
  PageHeader,
  StatCard,
  TableSearchBar,
} from "@/components/ui";
import { IconPlus, IconTicket } from "@/components/ui/icons";
import { cn } from "@/utils/cn";

type StatusFilter = "all" | TicketStatus;

export function TicketsPage() {
  const qc = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const deepLinkId = searchParams.get("t");
  const [selectedId, setSelectedId] = useState<string | null>(deepLinkId);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({
    conversation_id: "",
    priority: "NORMAL" as Priority,
    assigned_user_id: "",
    assigned_team_id: "",
  });
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [saveErr, setSaveErr] = useState<string | null>(null);

  const tickets = useQuery({
    queryKey: ["tickets"],
    queryFn: () => api<Ticket[]>("/tickets"),
  });

  const conversations = useQuery({
    queryKey: ["conversations", "all"],
    queryFn: () => api<Conversation[]>("/conversations?view=all"),
  });

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

  useSupportSocket({
    token: localStorage.getItem("access_token"),
    onEvent: (event) => {
      if (event.name?.startsWith("ticket.")) {
        void qc.invalidateQueries({ queryKey: ["tickets"] });
      }
    },
  });

  const customerName = (convId: string) => {
    const conv = conversations.data?.find((c) => c.id === convId);
    if (!conv) return "Unknown";
    return customers.data?.find((c) => c.id === conv.customer_id)?.name ?? "Customer";
  };

  const filtered = useMemo(() => {
    let list = tickets.data ?? [];
    if (statusFilter !== "all") {
      list = list.filter((t) => t.status === statusFilter);
    }
    const q = search.toLowerCase().trim();
    if (q) {
      list = list.filter((t) => {
        const name = customerName(t.conversation_id).toLowerCase();
        return (
          name.includes(q) ||
          t.status.toLowerCase().replace(/_/g, " ").includes(q) ||
          t.priority.toLowerCase().includes(q) ||
          t.id.toLowerCase().includes(q)
        );
      });
    }
    return list;
  }, [tickets.data, statusFilter, search, conversations.data, customers.data]); // eslint-disable-line react-hooks/exhaustive-deps -- customerName uses conv/customer maps

  useEffect(() => {
    if (!deepLinkId) return;
    setSelectedId(deepLinkId);
    const next = new URLSearchParams(searchParams);
    next.delete("t");
    setSearchParams(next, { replace: true });
  }, [deepLinkId]); // eslint-disable-line react-hooks/exhaustive-deps -- apply once per deep link

  const selected = useMemo(
    () => tickets.data?.find((t) => t.id === selectedId) ?? null,
    [tickets.data, selectedId]
  );

  const openCount = (tickets.data ?? []).filter((t) => t.status === "OPEN").length;
  const inProgressCount = (tickets.data ?? []).filter((t) => t.status === "IN_PROGRESS").length;
  const resolvedCount = (tickets.data ?? []).filter((t) => t.status === "RESOLVED").length;

  const userName = (id: string | null) =>
    id ? (users.data?.find((u) => u.id === id)?.full_name ?? "Unknown") : "Unassigned";

  const teamName = (id: string | null) =>
    id ? (teams.data?.find((t) => t.id === id)?.name ?? "Unknown") : "No team";

  const createTicket = useMutation({
    mutationFn: () =>
      api<Ticket>("/tickets", {
        method: "POST",
        body: JSON.stringify({
          conversation_id: createForm.conversation_id,
          priority: createForm.priority,
          assigned_user_id: createForm.assigned_user_id || null,
          assigned_team_id: createForm.assigned_team_id || null,
        }),
      }),
    onSuccess: (ticket) => {
      setShowCreate(false);
      setCreateForm({ conversation_id: "", priority: "NORMAL", assigned_user_id: "", assigned_team_id: "" });
      setSelectedId(ticket.id);
      setSaveMsg("Ticket created.");
      setSaveErr(null);
      void qc.invalidateQueries({ queryKey: ["tickets"] });
    },
    onError: (e) => {
      setSaveErr(e instanceof ApiError ? e.message : "Failed to create ticket.");
      setSaveMsg(null);
    },
  });

  const patchTicket = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api<Ticket>(`/tickets/${selectedId}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      setSaveMsg("Ticket updated.");
      setSaveErr(null);
      void qc.invalidateQueries({ queryKey: ["tickets"] });
    },
    onError: (e) => {
      setSaveErr(e instanceof ApiError ? e.message : "Failed to update ticket.");
      setSaveMsg(null);
    },
  });

  return (
    <div className="page-full">
      <div className="page-top">
        <PageHeader
          title="Tickets"
          description="Track escalations and manual support cases. Assign agents, update status, and resolve issues."
          action={
            <button type="button" className="btn btn-primary" onClick={() => setShowCreate(true)}>
              <IconPlus size={16} />
              New Ticket
            </button>
          }
        />

        <div className="stats-grid" style={{ marginBottom: "1rem" }}>
          <StatCard icon={<IconTicket size={20} />} value={tickets.data?.length ?? 0} label="Total Tickets" color="green" />
          <StatCard icon={<IconTicket size={20} />} value={openCount} label="Open" sublabel="Awaiting action" color="orange" />
          <StatCard icon={<IconTicket size={20} />} value={inProgressCount} label="In Progress" color="purple" />
          <StatCard icon={<IconTicket size={20} />} value={resolvedCount} label="Resolved" color="blue" />
        </div>

        {saveMsg && <Alert type="success">{saveMsg}</Alert>}
        {saveErr && <Alert type="error">{saveErr}</Alert>}

        <div className="filter-pills mb-4">
          <button
            type="button"
            className={cn("filter-pill", statusFilter === "all" && "active")}
            onClick={() => setStatusFilter("all")}
          >
            All ({tickets.data?.length ?? 0})
          </button>
          {TICKET_STATUSES.map((s) => (
            <button
              key={s}
              type="button"
              className={cn("filter-pill", statusFilter === s && "active")}
              onClick={() => setStatusFilter(s)}
            >
              {s.replace(/_/g, " ")}
            </button>
          ))}
        </div>
      </div>

      <div className="split-layout" style={{ borderTop: "1px solid var(--border)" }}>
        <section className="split-list">
          <TableSearchBar
            value={search}
            placeholder="Search tickets…"
            onChange={setSearch}
          />
          {tickets.isLoading && <LoadingState message="Loading tickets…" />}
          {tickets.isError && (
            <div style={{ padding: "1rem" }}>
              <Alert type="error">
                {tickets.error instanceof ApiError ? tickets.error.message : "Failed to load tickets."}
              </Alert>
            </div>
          )}
          {!tickets.isLoading && !filtered.length && (
            <EmptyState
              message={
                search.trim()
                  ? "No tickets match your search."
                  : "No tickets yet. AI escalations create tickets automatically, or create one manually."
              }
            />
          )}
          {filtered.map((t) => (
            <button
              key={t.id}
              type="button"
              className={cn("list-item", selectedId === t.id && "selected")}
              onClick={() => {
                setSelectedId(t.id);
                setSaveMsg(null);
                setSaveErr(null);
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" }}>
                <span className="list-item-title">{customerName(t.conversation_id)}</span>
                <span className={statusClass(t.status.toLowerCase())}>{t.status.replace(/_/g, " ")}</span>
              </div>
              <div className="list-item-meta">
                <span className={statusClass(t.priority.toLowerCase())}>{t.priority}</span>
                <span>{formatRelative(t.created_at)}</span>
              </div>
            </button>
          ))}
        </section>

        <section className="split-detail">
          {!selected && <EmptyState message="Select a ticket to view details and update status." />}
          {selected && (
            <div className="page-scroll">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem", marginBottom: "1.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                  <Avatar name={customerName(selected.conversation_id)} />
                  <div>
                    <h2 style={{ margin: 0, fontSize: "1.125rem", fontWeight: 700 }}>
                      {customerName(selected.conversation_id)}
                    </h2>
                    <div className="flex gap-2 mt-4" style={{ marginTop: "0.375rem" }}>
                      <span className={statusClass(selected.status.toLowerCase())}>{selected.status.replace(/_/g, " ")}</span>
                      <span className={statusClass(selected.priority.toLowerCase())}>{selected.priority}</span>
                    </div>
                  </div>
                </div>
              </div>

              <dl className="meta-grid mb-6">
                <div><dt>Ticket ID</dt><dd><code>{selected.id}</code></dd></div>
                <div>
                  <dt>Conversation</dt>
                  <dd>
                    <Link to={`/?c=${selected.conversation_id}`}>Open in Inbox</Link>
                  </dd>
                </div>
                <div><dt>Created</dt><dd>{formatDate(selected.created_at)}</dd></div>
                <div><dt>Resolved</dt><dd>{formatDate(selected.resolved_at)}</dd></div>
                <div><dt>Closed</dt><dd>{formatDate(selected.closed_at)}</dd></div>
                <div><dt>Assignee</dt><dd>{userName(selected.assigned_user_id)}</dd></div>
                <div><dt>Team</dt><dd>{teamName(selected.assigned_team_id)}</dd></div>
              </dl>

              <div className="card">
                <h3 className="section-title">Update Ticket</h3>
                <div className="grid-2" style={{ marginBottom: "1rem" }}>
                  <div className="form-field">
                    <label className="form-label" htmlFor="edit-status">Status</label>
                    <select
                      id="edit-status"
                      className="form-select"
                      value={selected.status}
                      onChange={(e) => patchTicket.mutate({ status: e.target.value as TicketStatus })}
                      disabled={patchTicket.isPending}
                    >
                      {TICKET_STATUSES.map((s) => (
                        <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-field">
                    <label className="form-label" htmlFor="edit-priority">Priority</label>
                    <select
                      id="edit-priority"
                      className="form-select"
                      value={selected.priority}
                      onChange={(e) => patchTicket.mutate({ priority: e.target.value as Priority })}
                      disabled={patchTicket.isPending}
                    >
                      {PRIORITIES.map((p) => (
                        <option key={p} value={p}>{p}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-field">
                    <label className="form-label" htmlFor="edit-assignee">Assignee</label>
                    <select
                      id="edit-assignee"
                      className="form-select"
                      value={selected.assigned_user_id ?? ""}
                      onChange={(e) => patchTicket.mutate({ assigned_user_id: e.target.value || null })}
                      disabled={patchTicket.isPending}
                    >
                      <option value="">Unassigned</option>
                      {(users.data ?? []).map((u) => (
                        <option key={u.id} value={u.id}>{u.full_name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-field">
                    <label className="form-label" htmlFor="edit-team">Team</label>
                    <select
                      id="edit-team"
                      className="form-select"
                      value={selected.assigned_team_id ?? ""}
                      onChange={(e) => patchTicket.mutate({ assigned_team_id: e.target.value || null })}
                      disabled={patchTicket.isPending}
                    >
                      <option value="">No team</option>
                      {(teams.data ?? []).map((t) => (
                        <option key={t.id} value={t.id}>{t.name}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="flex gap-2">
                  {selected.status !== "RESOLVED" && selected.status !== "CLOSED" && (
                    <button type="button" className="btn btn-secondary btn-sm" disabled={patchTicket.isPending} onClick={() => patchTicket.mutate({ status: "RESOLVED" })}>
                      Mark Resolved
                    </button>
                  )}
                  {selected.status !== "CLOSED" && (
                    <button type="button" className="btn btn-danger btn-sm" disabled={patchTicket.isPending} onClick={() => patchTicket.mutate({ status: "CLOSED" })}>
                      Close Ticket
                    </button>
                  )}
                  {selected.status === "CLOSED" && (
                    <button type="button" className="btn btn-secondary btn-sm" disabled={patchTicket.isPending} onClick={() => patchTicket.mutate({ status: "OPEN" })}>
                      Reopen
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}
        </section>
      </div>

      {showCreate && (
        <Modal
          title="Create Ticket"
          onClose={() => setShowCreate(false)}
          footer={
            <>
              <button type="button" className="btn btn-ghost" onClick={() => setShowCreate(false)}>Cancel</button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={createTicket.isPending || !createForm.conversation_id}
                onClick={() => createTicket.mutate()}
              >
                Create Ticket
              </button>
            </>
          }
        >
          <div className="form-field">
            <label className="form-label" htmlFor="conv-id">Conversation *</label>
            <select
              id="conv-id"
              className="form-select"
              value={createForm.conversation_id}
              onChange={(e) => setCreateForm((f) => ({ ...f, conversation_id: e.target.value }))}
            >
              <option value="">Select conversation…</option>
              {(conversations.data ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {customerName(c.id)} — {c.status} · {c.priority}
                </option>
              ))}
            </select>
          </div>
          <div className="grid-2">
            <div className="form-field">
              <label className="form-label">Priority</label>
              <select
                className="form-select"
                value={createForm.priority}
                onChange={(e) => setCreateForm((f) => ({ ...f, priority: e.target.value as Priority }))}
              >
                {PRIORITIES.map((p) => (<option key={p} value={p}>{p}</option>))}
              </select>
            </div>
            <div className="form-field">
              <label className="form-label">Assignee</label>
              <select
                className="form-select"
                value={createForm.assigned_user_id}
                onChange={(e) => setCreateForm((f) => ({ ...f, assigned_user_id: e.target.value }))}
              >
                <option value="">Unassigned</option>
                {(users.data ?? []).map((u) => (<option key={u.id} value={u.id}>{u.full_name}</option>))}
              </select>
            </div>
          </div>
          <div className="form-field">
            <label className="form-label">Team</label>
            <select
              className="form-select"
              value={createForm.assigned_team_id}
              onChange={(e) => setCreateForm((f) => ({ ...f, assigned_team_id: e.target.value }))}
            >
              <option value="">No team</option>
              {(teams.data ?? []).map((t) => (<option key={t.id} value={t.id}>{t.name}</option>))}
            </select>
          </div>
        </Modal>
      )}
    </div>
  );
}
