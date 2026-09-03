import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/services/api/client";
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
import {
  IconBuilding,
  IconCopy,
  IconMail,
  IconMessage,
  IconPhone,
  IconPlus,
  IconTicket,
  IconUsers,
} from "@/components/ui/icons";
import { formatDate } from "@/utils/format";
import { useNavigate } from "react-router-dom";
import type { Conversation, Customer, Ticket } from "@/types";

const schema = z.object({
  name: z.string().min(1, "Name is required"),
  email: z.string().email().optional().or(z.literal("")),
  phone: z.string().optional(),
  company_name: z.string().optional(),
});

type Form = z.infer<typeof schema>;

const PAGE_SIZE = 10;

export function CustomersPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const customers = useQuery({
    queryKey: ["customers"],
    queryFn: () => api<Customer[]>("/customers"),
  });

  const conversations = useQuery({
    queryKey: ["conversations", "all"],
    queryFn: () => api<Conversation[]>("/conversations?view=all"),
  });

  const tickets = useQuery({
    queryKey: ["tickets"],
    queryFn: () => api<Ticket[]>("/tickets"),
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<Form>({ resolver: zodResolver(schema) });

  const create = useMutation({
    mutationFn: (body: Form) =>
      api<Customer>("/customers", {
        method: "POST",
        body: JSON.stringify({
          name: body.name,
          email: body.email || null,
          phone: body.phone || null,
          company_name: body.company_name || null,
        }),
      }),
    onSuccess: () => {
      reset();
      setShowCreate(false);
      void qc.invalidateQueries({ queryKey: ["customers"] });
    },
  });

  const convCount = (customerId: string) =>
    (conversations.data ?? []).filter((c) => c.customer_id === customerId).length;

  const ticketCount = (customerId: string) => {
    const convIds = new Set(
      (conversations.data ?? []).filter((c) => c.customer_id === customerId).map((c) => c.id)
    );
    return (tickets.data ?? []).filter((t) => convIds.has(t.conversation_id)).length;
  };

  const companies = useMemo(() => {
    const set = new Set<string>();
    (customers.data ?? []).forEach((c) => {
      if (c.company_name) set.add(c.company_name);
    });
    return set.size;
  }, [customers.data]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    let list = customers.data ?? [];
    if (q) {
      list = list.filter(
        (c) =>
          c.name.toLowerCase().includes(q) ||
          c.email?.toLowerCase().includes(q) ||
          c.phone?.includes(q) ||
          c.company_name?.toLowerCase().includes(q)
      );
    }
    return list;
  }, [customers.data, search]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paged = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const copyId = (id: string) => {
    void navigator.clipboard.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div className="page-scroll">
      <PageHeader
        title="Customers"
        description="Manage your customer records, view contact details, and track conversations and tickets."
        action={
          <button type="button" className="btn btn-primary" onClick={() => setShowCreate(true)}>
            <IconPlus size={16} />
            Create Customer
          </button>
        }
      />

      <div className="stats-grid">
        <StatCard
          icon={<IconUsers size={20} />}
          value={customers.data?.length ?? 0}
          label="Total Customers"
          sublabel="All customers in the system"
          color="green"
        />
        <StatCard
          icon={<IconMessage size={20} />}
          value={conversations.data?.length ?? 0}
          label="Conversations"
          sublabel="Across all customers"
          color="purple"
        />
        <StatCard
          icon={<IconTicket size={20} />}
          value={tickets.data?.length ?? 0}
          label="Tickets"
          sublabel="Linked to customer conversations"
          color="orange"
        />
        <StatCard
          icon={<IconBuilding size={20} />}
          value={companies}
          label="Companies"
          sublabel="Unique company names"
          color="blue"
        />
      </div>

      {create.isSuccess && !create.isPending && (
        <Alert type="success">Customer created successfully.</Alert>
      )}
      {create.isError && (
        <Alert type="error">
          {create.error instanceof ApiError ? create.error.message : "Failed to create customer."}
        </Alert>
      )}

      <div className="table-wrap">
        <TableSearchBar
          value={search}
          placeholder="Search customers…"
          onChange={(value) => {
            setSearch(value);
            setPage(1);
          }}
          onReset={() => setPage(1)}
        />

        {customers.isLoading && <LoadingState message="Loading customers…" />}
        {customers.isError && (
          <div style={{ padding: "1rem 1.25rem" }}>
            <Alert type="error">
              {customers.error instanceof ApiError
                ? customers.error.message
                : "Failed to load customers."}
            </Alert>
          </div>
        )}

        {!customers.isLoading && !filtered.length && (
          <EmptyState message="No customers yet. Create one to start a Web Chat session." />
        )}

        {!customers.isLoading && filtered.length > 0 && (
          <table className="data-table">
            <thead>
              <tr>
                <th>Customer</th>
                <th>Contact</th>
                <th>Company</th>
                <th>Conversations</th>
                <th>Tickets</th>
                <th>Created</th>
                <th>ID</th>
              </tr>
            </thead>
            <tbody>
              {paged.map((c) => (
                <tr
                  key={c.id}
                  className="table-row-clickable"
                  onClick={() => navigate(`/customers/${c.id}`)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      navigate(`/customers/${c.id}`);
                    }
                  }}
                  tabIndex={0}
                  role="link"
                  aria-label={`Open customer ${c.name}`}
                >
                  <td>
                    <div className="cell-with-avatar">
                      <Avatar name={c.name} size="sm" />
                      <div className="cell-stack">
                        <span className="cell-primary">{c.name}</span>
                      </div>
                    </div>
                  </td>
                  <td>
                    <div className="cell-stack">
                      {c.email && (
                        <span className="text-sm flex items-center gap-2">
                          <IconMail /> {c.email}
                        </span>
                      )}
                      {c.phone && (
                        <span className="text-sm text-muted flex items-center gap-2">
                          <IconPhone /> {c.phone}
                        </span>
                      )}
                      {!c.email && !c.phone && <span className="text-muted">—</span>}
                    </div>
                  </td>
                  <td>{c.company_name ?? <span className="text-muted">—</span>}</td>
                  <td>
                    <span className={`badge-count ${convCount(c.id) ? "green" : "muted"}`}>
                      {convCount(c.id)}
                    </span>
                  </td>
                  <td>
                    <span className={`badge-count ${ticketCount(c.id) ? "orange" : "muted"}`}>
                      {ticketCount(c.id)}
                    </span>
                  </td>
                  <td className="text-sm text-muted">{formatDate(c.created_at)}</td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        copyId(c.id);
                      }}
                      title="Copy customer ID for Web Chat"
                    >
                      <IconCopy size={14} />
                      {copiedId === c.id ? "Copied" : c.id.slice(0, 8) + "…"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {filtered.length > 0 && (
          <div className="table-footer">
            <span>
              Showing {(page - 1) * PAGE_SIZE + 1} to {Math.min(page * PAGE_SIZE, filtered.length)} of{" "}
              {filtered.length} customers
            </span>
            <div className="table-pagination">
              <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                ‹
              </button>
              {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                <button
                  key={p}
                  type="button"
                  className={p === page ? "active" : ""}
                  onClick={() => setPage(p)}
                >
                  {p}
                </button>
              ))}
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                ›
              </button>
            </div>
          </div>
        )}
      </div>

      {showCreate && (
        <Modal
          title="Create Customer"
          onClose={() => setShowCreate(false)}
          footer={
            <>
              <button type="button" className="btn btn-ghost" onClick={() => setShowCreate(false)}>
                Cancel
              </button>
              <button
                type="submit"
                form="create-customer-form"
                className="btn btn-primary"
                disabled={isSubmitting || create.isPending}
              >
                Create Customer
              </button>
            </>
          }
        >
          <form
            id="create-customer-form"
            onSubmit={handleSubmit((v) => create.mutate(v))}
            style={{ display: "grid", gap: "1rem" }}
          >
            <div className="form-field">
              <label className="form-label" htmlFor="c-name">Name *</label>
              <input id="c-name" className="form-input" placeholder="Full name" {...register("name")} />
              {errors.name && <span className="form-error">{errors.name.message}</span>}
            </div>
            <div className="form-field">
              <label className="form-label" htmlFor="c-email">Email</label>
              <input id="c-email" type="email" className="form-input" placeholder="email@example.com" {...register("email")} />
            </div>
            <div className="form-field">
              <label className="form-label" htmlFor="c-phone">Phone</label>
              <input id="c-phone" className="form-input" placeholder="+1 555 0100" {...register("phone")} />
            </div>
            <div className="form-field">
              <label className="form-label" htmlFor="c-company">Company</label>
              <input id="c-company" className="form-input" placeholder="Company name" {...register("company_name")} />
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
