import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "@/services/api/client";
import {
  Alert,
  Avatar,
  EmptyState,
  LoadingState,
  StatCard,
} from "@/components/ui";
import {
  IconBuilding,
  IconChevronLeft,
  IconCopy,
  IconMail,
  IconMessage,
  IconPhone,
  IconTicket,
} from "@/components/ui/icons";
import { formatDate, formatMessageTime, statusClass } from "@/utils/format";
import { cn } from "@/utils/cn";
import { useState } from "react";

type Customer360 = {
  customer: {
    id: string;
    name: string;
    email: string | null;
    phone: string | null;
    company_name: string | null;
    created_at: string;
    updated_at: string;
  };
  conversations: {
    id: string;
    channel: string;
    subject: string | null;
    status: string;
    updated_at: string;
  }[];
  tickets: {
    id: string;
    status: string;
    priority: string;
    source: string;
    created_at: string;
  }[];
  timeline: {
    id: string;
    type: string;
    channel: string | null;
    content: string;
    created_at: string;
  }[];
};

function formatLabel(value: string): string {
  return value.replace(/_/g, " ");
}

function timelineSenderLabel(type: string): string {
  if (type === "AI") return "AI Support";
  if (type === "AGENT") return "Agent";
  if (type === "CUSTOMER") return "Customer";
  if (type === "SYSTEM") return "System";
  return formatLabel(type);
}

export function CustomerDetailPage() {
  const { customerId } = useParams();
  const [copiedId, setCopiedId] = useState(false);

  const detail = useQuery({
    queryKey: ["customer-360", customerId],
    queryFn: () => api<Customer360>(`/customers/${customerId}/360`),
    enabled: !!customerId,
  });

  const copyId = () => {
    if (!detail.data?.customer.id) return;
    void navigator.clipboard.writeText(detail.data.customer.id);
    setCopiedId(true);
    setTimeout(() => setCopiedId(false), 2000);
  };

  if (detail.isLoading) return <LoadingState message="Loading customer…" />;

  if (detail.isError) {
    return (
      <div className="page-scroll">
        <Alert type="error">
          {detail.error instanceof ApiError ? detail.error.message : "Failed to load customer."}
        </Alert>
        <Link to="/customers" className="btn btn-secondary mt-4">
          Back to customers
        </Link>
      </div>
    );
  }

  if (!detail.data) return null;

  const { customer, conversations, tickets, timeline } = detail.data;
  const channels = [...new Set(conversations.map((c) => c.channel))];

  return (
    <div className="page-scroll">
      <Link to="/customers" className="back-link">
        <IconChevronLeft size={16} />
        All customers
      </Link>

      <div className="customer-header mb-6">
        <Avatar name={customer.name} size="lg" />
        <div>
          <h1 className="page-title">{customer.name}</h1>
          {customer.email && <p className="page-desc">{customer.email}</p>}
        </div>
      </div>

      <div className="stats-grid">
        <StatCard
          icon={<IconMessage size={20} />}
          value={conversations.length}
          label="Conversations"
          sublabel={channels.length ? channels.map(formatLabel).join(", ") : "No channels yet"}
          color="purple"
        />
        <StatCard
          icon={<IconTicket size={20} />}
          value={tickets.length}
          label="Tickets"
          sublabel="Linked to this customer"
          color="orange"
        />
        <StatCard
          icon={<IconBuilding size={20} />}
          value={customer.company_name ?? "—"}
          label="Company"
          sublabel={`Customer since ${formatDate(customer.created_at)}`}
          color="blue"
        />
      </div>

      <div className="grid-2 mb-6">
        <section className="card">
          <h2 className="section-title">Profile</h2>
          <dl className="meta-grid">
            <div className="meta-grid-full">
              <dt>Email</dt>
              <dd>
                {customer.email ? (
                  <span className="flex items-center gap-2">
                    <IconMail size={14} />
                    {customer.email}
                  </span>
                ) : (
                  "—"
                )}
              </dd>
            </div>
            <div>
              <dt>Phone</dt>
              <dd>
                {customer.phone ? (
                  <span className="flex items-center gap-2">
                    <IconPhone size={14} />
                    {customer.phone}
                  </span>
                ) : (
                  "—"
                )}
              </dd>
            </div>
            <div>
              <dt>Company</dt>
              <dd>{customer.company_name ?? "—"}</dd>
            </div>
            <div>
              <dt>Created</dt>
              <dd>{formatDate(customer.created_at)}</dd>
            </div>
            <div className="meta-grid-full">
              <dt>Customer ID</dt>
              <dd>
                <button type="button" className="btn btn-ghost btn-sm" onClick={copyId}>
                  <IconCopy size={14} />
                  {copiedId ? "Copied" : `${customer.id.slice(0, 8)}…`}
                </button>
              </dd>
            </div>
          </dl>
        </section>

        <section className="card">
          <h2 className="section-title">Recent activity</h2>
          {timeline.length === 0 ? (
            <p className="form-hint">No messages yet.</p>
          ) : (
            <div className="timeline-preview">
              {timeline.slice(0, 3).map((item) => (
                <div key={item.id} className="timeline-preview-item">
                  <span className={statusClass(item.type.toLowerCase())}>
                    {timelineSenderLabel(item.type)}
                  </span>
                  <span className="text-sm text-muted">{formatMessageTime(item.created_at)}</span>
                  <p className="timeline-preview-text">{item.content}</p>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      <section className="card mb-6">
        <h2 className="section-title">Conversations</h2>
        {conversations.length === 0 ? (
          <EmptyState message="No conversations yet for this customer." />
        ) : (
          <div className="table-wrap card-flush">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Channel</th>
                  <th>Subject</th>
                  <th>Status</th>
                  <th>Updated</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {conversations.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <span className="badge badge-normal">{formatLabel(c.channel)}</span>
                    </td>
                    <td>{c.subject ?? "No subject"}</td>
                    <td>
                      <span className={statusClass(c.status.toLowerCase())}>{formatLabel(c.status)}</span>
                    </td>
                    <td className="text-sm text-muted">{formatDate(c.updated_at)}</td>
                    <td>
                      <Link to={`/?c=${c.id}`} className="btn btn-secondary btn-sm">
                        Open in inbox
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card mb-6">
        <h2 className="section-title">Tickets</h2>
        {tickets.length === 0 ? (
          <EmptyState message="No tickets for this customer." />
        ) : (
          <div className="table-wrap card-flush">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Priority</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {tickets.map((t) => (
                  <tr key={t.id}>
                    <td>{formatLabel(t.source)}</td>
                    <td>
                      <span className={statusClass(t.priority.toLowerCase())}>{formatLabel(t.priority)}</span>
                    </td>
                    <td>
                      <span className={statusClass(t.status.toLowerCase())}>{formatLabel(t.status)}</span>
                    </td>
                    <td className="text-sm text-muted">{formatDate(t.created_at)}</td>
                    <td>
                      <Link to={`/tickets?t=${t.id}`} className="btn btn-secondary btn-sm">
                        View ticket
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <h2 className="section-title">Timeline</h2>
        {timeline.length === 0 ? (
          <EmptyState message="No activity recorded yet." />
        ) : (
          <div className="timeline-feed">
            {timeline.map((item) => (
              <article
                key={item.id}
                className={cn("timeline-item", `timeline-item-${item.type.toLowerCase()}`)}
              >
                <div className="timeline-item-header">
                  <span className={statusClass(item.type.toLowerCase())}>
                    {timelineSenderLabel(item.type)}
                  </span>
                  {item.channel && (
                    <span className="badge badge-normal">{formatLabel(item.channel)}</span>
                  )}
                  <time className="text-sm text-muted" dateTime={item.created_at}>
                    {formatDate(item.created_at)}
                  </time>
                </div>
                <p className="timeline-item-content">{item.content}</p>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
