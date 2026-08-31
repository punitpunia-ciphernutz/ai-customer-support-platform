import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/services/api/client";
import { formatDate } from "@/utils/format";
import type { Team, UserListItem } from "@/types";
import {
  Alert,
  Avatar,
  EmptyState,
  LoadingState,
  Modal,
  PageHeader,
  StatCard,
} from "@/components/ui";
import { IconPlus, IconTeam, IconUsers } from "@/components/ui/icons";
import { cn } from "@/utils/cn";

const schema = z.object({
  name: z.string().min(1, "Name is required").max(255),
  description: z.string().optional(),
});

type Form = z.infer<typeof schema>;

export function TeamsPage() {
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [saveErr, setSaveErr] = useState<string | null>(null);

  const teams = useQuery({
    queryKey: ["teams"],
    queryFn: () => api<Team[]>("/teams"),
  });

  const users = useQuery({
    queryKey: ["users"],
    queryFn: () => api<UserListItem[]>("/users"),
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<Form>({ resolver: zodResolver(schema) });

  const create = useMutation({
    mutationFn: (body: Form) =>
      api<Team>("/teams", {
        method: "POST",
        body: JSON.stringify({
          name: body.name,
          description: body.description?.trim() || null,
        }),
      }),
    onSuccess: () => {
      reset();
      setShowCreate(false);
      setSaveMsg("Team created.");
      setSaveErr(null);
      void qc.invalidateQueries({ queryKey: ["teams"] });
    },
    onError: (e) => {
      setSaveErr(e instanceof ApiError ? e.message : "Failed to create team.");
      setSaveMsg(null);
    },
  });

  const activeUsers = (users.data ?? []).filter((u) => u.is_active).length;

  return (
    <div className="page-scroll">
      <PageHeader
        title="Teams"
        description="Organize agents into teams for routing escalations. Team assignment is used by the AI agent when escalating conversations."
        action={
          <button type="button" className="btn btn-primary" onClick={() => setShowCreate(true)}>
            <IconPlus size={16} />
            Create Team
          </button>
        }
      />

      <div className="stats-grid">
        <StatCard icon={<IconTeam size={20} />} value={teams.data?.length ?? 0} label="Total Teams" color="green" />
        <StatCard icon={<IconUsers size={20} />} value={users.data?.length ?? 0} label="Org Members" color="purple" />
        <StatCard icon={<IconUsers size={20} />} value={activeUsers} label="Active Members" color="blue" />
      </div>

      {saveMsg && <Alert type="success">{saveMsg}</Alert>}
      {saveErr && <Alert type="error">{saveErr}</Alert>}

      <h2 className="section-title">Teams</h2>
      {teams.isLoading && <LoadingState message="Loading teams…" />}
      {teams.isError && (
        <Alert type="error">
          {teams.error instanceof ApiError ? teams.error.message : "Failed to load teams."}
        </Alert>
      )}
      {!teams.isLoading && !teams.data?.length && (
        <EmptyState message="No teams yet. Create one above — the seed data includes a Billing team." />
      )}

      <div className="grid-2 mb-6">
        {(teams.data ?? []).map((t) => (
          <div key={t.id} className="card">
            <div className="flex justify-between items-center mb-4">
              <div className="flex items-center gap-3">
                <div className="stat-icon green" style={{ width: 36, height: 36 }}>
                  <IconTeam size={18} />
                </div>
                <div>
                  <div style={{ fontWeight: 700, fontSize: "1rem" }}>{t.name}</div>
                  <div className="text-sm text-muted">{formatDate(t.created_at)}</div>
                </div>
              </div>
            </div>
            {t.description && (
              <p className="text-sm text-muted" style={{ margin: "0 0 0.75rem" }}>{t.description}</p>
            )}
            <code className="text-sm" style={{ color: "var(--text-muted)" }}>{t.id}</code>
          </div>
        ))}
      </div>

      <h2 className="section-title">Organization Members</h2>
      <p className="form-hint mb-4">
        Users available for assignment. Team membership management is not yet available via API.
      </p>
      {users.isLoading && <LoadingState message="Loading users…" />}
      {users.isError && (
        <Alert type="error">
          {users.error instanceof ApiError ? users.error.message : "Failed to load users."}
        </Alert>
      )}

      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Member</th>
              <th>Email</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {(users.data ?? []).map((u) => (
              <tr key={u.id}>
                <td>
                  <div className="cell-with-avatar">
                    <Avatar name={u.full_name} size="sm" />
                    <span className="cell-primary">{u.full_name}</span>
                  </div>
                </td>
                <td className="text-sm text-muted">{u.email}</td>
                <td>
                  <span className={cn("badge", u.is_active ? "badge-open" : "badge-closed")}>
                    {u.is_active ? "Active" : "Inactive"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!users.isLoading && !users.data?.length && (
          <EmptyState message="No users found." />
        )}
      </div>

      {showCreate && (
        <Modal
          title="Create Team"
          onClose={() => setShowCreate(false)}
          footer={
            <>
              <button type="button" className="btn btn-ghost" onClick={() => setShowCreate(false)}>Cancel</button>
              <button
                type="submit"
                form="create-team-form"
                className="btn btn-primary"
                disabled={isSubmitting || create.isPending}
              >
                Create Team
              </button>
            </>
          }
        >
          <form id="create-team-form" onSubmit={handleSubmit((v) => create.mutate(v))} style={{ display: "grid", gap: "1rem" }}>
            <div className="form-field">
              <label className="form-label" htmlFor="team-name">Name *</label>
              <input id="team-name" className="form-input" placeholder="e.g. Billing, Support" {...register("name")} />
              {errors.name && <span className="form-error">{errors.name.message}</span>}
            </div>
            <div className="form-field">
              <label className="form-label" htmlFor="team-desc">Description</label>
              <input id="team-desc" className="form-input" placeholder="Optional description" {...register("description")} />
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
