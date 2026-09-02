import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "@/services/api/client";
import { Alert, LoadingState, PageHeader } from "@/components/ui";
import { formatDate } from "@/utils/format";

type Customer360 = {
  customer: {
    id: string;
    name: string;
    email: string | null;
    phone: string | null;
    company_name: string | null;
  };
  conversations: { id: string; channel: string; subject: string | null; status: string; updated_at: string }[];
  tickets: { id: string; status: string; priority: string; source: string; created_at: string }[];
  timeline: { id: string; type: string; channel: string | null; content: string; created_at: string }[];
};

export function CustomerDetailPage() {
  const { customerId } = useParams();
  const detail = useQuery({
    queryKey: ["customer-360", customerId],
    queryFn: () => api<Customer360>(`/customers/${customerId}/360`),
    enabled: !!customerId,
  });

  if (detail.isLoading) return <LoadingState message="Loading customer…" />;
  if (detail.isError) {
    return (
      <Alert type="error">
        {detail.error instanceof ApiError ? detail.error.message : "Failed to load customer."}
      </Alert>
    );
  }
  if (!detail.data) return null;

  const { customer, conversations, tickets, timeline } = detail.data;

  return (
    <div className="page">
      <PageHeader
        title={customer.name}
        description={customer.email ?? "No email on file"}
        action={<Link className="btn btn-secondary btn-sm" to="/customers">← All customers</Link>}
      />

      <div className="grid-2" style={{ marginBottom: "1.5rem" }}>
        <section className="card">
          <h2 className="section-title">Profile</h2>
          <dl className="detail-list">
            <div><dt>Email</dt><dd>{customer.email ?? "—"}</dd></div>
            <div><dt>Phone</dt><dd>{customer.phone ?? "—"}</dd></div>
            <div><dt>Company</dt><dd>{customer.company_name ?? "—"}</dd></div>
          </dl>
        </section>
        <section className="card">
          <h2 className="section-title">Summary</h2>
          <dl className="detail-list">
            <div><dt>Conversations</dt><dd>{conversations.length}</dd></div>
            <div><dt>Tickets</dt><dd>{tickets.length}</dd></div>
            <div><dt>Channels</dt><dd>{[...new Set(conversations.map((c) => c.channel))].join(", ") || "—"}</dd></div>
          </dl>
        </section>
      </div>

      <section className="card" style={{ marginBottom: "1.5rem" }}>
        <h2 className="section-title">Conversations</h2>
        {conversations.length === 0 ? <p className="text-muted">No conversations yet.</p> : (
          <ul className="simple-list">
            {conversations.map((c) => (
              <li key={c.id}>
                <Link to={`/?c=${c.id}`}>{c.channel.replace(/_/g, " ")} — {c.subject ?? "No subject"}</Link>
                <span className="text-sm text-muted"> · {c.status} · {formatDate(c.updated_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card" style={{ marginBottom: "1.5rem" }}>
        <h2 className="section-title">Tickets</h2>
        {tickets.length === 0 ? <p className="text-muted">No tickets.</p> : (
          <ul className="simple-list">
            {tickets.map((t) => (
              <li key={t.id}>
                {t.source} · {t.priority} · {t.status} · {formatDate(t.created_at)}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card">
        <h2 className="section-title">Timeline</h2>
        {timeline.length === 0 ? <p className="text-muted">No activity yet.</p> : (
          <ul className="simple-list">
            {timeline.map((item) => (
              <li key={item.id}>
                <strong>{item.type}</strong>
                {item.channel ? ` · ${item.channel.replace(/_/g, " ")}` : ""}
                {" · "}{formatDate(item.created_at)}
                <div className="text-sm text-muted">{item.content}</div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
