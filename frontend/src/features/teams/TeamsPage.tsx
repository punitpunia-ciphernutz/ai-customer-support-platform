import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/services/api/client";
import { formatDate } from "@/utils/format";
import type { Team, TeamDetail, TeamMember, UserListItem } from "@/types";
import { useAuth } from "@/features/auth/AuthContext";
import {
  Alert,
  Avatar,
  EmptyState,
  LoadingState,
  Modal,
  PageHeader,
  StatCard,
} from "@/components/ui";
import { IconPlus, IconTeam, IconTrash, IconUsers } from "@/components/ui/icons";
import { cn } from "@/utils/cn";

const schema = z.object({
  name: z.string().min(1, "Name is required").max(255),
  description: z.string().optional(),
});

type Form = z.infer<typeof schema>;

function membersForTeam(teamId: string, users: UserListItem[]): UserListItem[] {
  return users.filter((u) => (u.teams ?? []).some((t) => t.id === teamId));
}

export function TeamsPage() {
  const qc = useQueryClient();
  const { user } = useAuth();
  const canWrite = Boolean(user?.role.permissions.includes("teams.write"));

  const [showCreate, setShowCreate] = useState(false);
  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [addUserId, setAddUserId] = useState("");
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

  const teamDetail = useQuery({
    queryKey: ["teams", selectedTeamId],
    queryFn: () => api<TeamDetail>(`/teams/${selectedTeamId}`),
    enabled: Boolean(selectedTeamId),
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<Form>({ resolver: zodResolver(schema) });

  const {
    register: registerEdit,
    handleSubmit: handleEditSubmit,
    reset: resetEdit,
    formState: { errors: editErrors, isSubmitting: editSubmitting },
  } = useForm<Form>({ resolver: zodResolver(schema) });

  useEffect(() => {
    if (teamDetail.data) {
      resetEdit({
        name: teamDetail.data.name,
        description: teamDetail.data.description ?? "",
      });
    }
  }, [teamDetail.data, resetEdit]);

  const invalidateAll = () => {
    void qc.invalidateQueries({ queryKey: ["teams"] });
    void qc.invalidateQueries({ queryKey: ["users"] });
    if (selectedTeamId) {
      void qc.invalidateQueries({ queryKey: ["teams", selectedTeamId] });
    }
  };

  const create = useMutation({
    mutationFn: (body: Form) =>
      api<Team>("/teams", {
        method: "POST",
        body: JSON.stringify({
          name: body.name,
          description: body.description?.trim() || null,
        }),
      }),
    onSuccess: (team) => {
      reset();
      setShowCreate(false);
      setSaveMsg("Team created.");
      setSaveErr(null);
      invalidateAll();
      setSelectedTeamId(team.id);
      setEditing(false);
    },
    onError: (e) => {
      setSaveErr(e instanceof ApiError ? e.message : "Failed to create team.");
      setSaveMsg(null);
    },
  });

  const update = useMutation({
    mutationFn: (body: Form) =>
      api<Team>(`/teams/${selectedTeamId}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: body.name,
          description: body.description?.trim() || null,
        }),
      }),
    onSuccess: () => {
      setEditing(false);
      setSaveMsg("Team updated.");
      setSaveErr(null);
      invalidateAll();
    },
    onError: (e) => {
      setSaveErr(e instanceof ApiError ? e.message : "Failed to update team.");
      setSaveMsg(null);
    },
  });

  const removeTeam = useMutation({
    mutationFn: (teamId: string) => api(`/teams/${teamId}`, { method: "DELETE" }),
    onSuccess: () => {
      setSelectedTeamId(null);
      setSaveMsg("Team deleted.");
      setSaveErr(null);
      invalidateAll();
    },
    onError: (e) => {
      setSaveErr(e instanceof ApiError ? e.message : "Failed to delete team.");
      setSaveMsg(null);
    },
  });

  const addMember = useMutation({
    mutationFn: (userId: string) =>
      api<TeamMember>(`/teams/${selectedTeamId}/members`, {
        method: "POST",
        body: JSON.stringify({ user_id: userId }),
      }),
    onSuccess: () => {
      setAddUserId("");
      setSaveMsg("Member added.");
      setSaveErr(null);
      invalidateAll();
    },
    onError: (e) => {
      setSaveErr(e instanceof ApiError ? e.message : "Failed to add member.");
      setSaveMsg(null);
    },
  });

  const removeMember = useMutation({
    mutationFn: (userId: string) =>
      api(`/teams/${selectedTeamId}/members/${userId}`, { method: "DELETE" }),
    onSuccess: () => {
      setSaveMsg("Member removed.");
      setSaveErr(null);
      invalidateAll();
    },
    onError: (e) => {
      setSaveErr(e instanceof ApiError ? e.message : "Failed to remove member.");
      setSaveMsg(null);
    },
  });

  const activeUsers = (users.data ?? []).filter((u) => u.is_active).length;

  const addableUsers = useMemo(() => {
    const memberIds = new Set((teamDetail.data?.members ?? []).map((m) => m.user_id));
    return (users.data ?? []).filter((u) => u.is_active && !memberIds.has(u.id));
  }, [teamDetail.data?.members, users.data]);

  const closeDetail = () => {
    setSelectedTeamId(null);
    setEditing(false);
    setAddUserId("");
  };

  return (
    <div className="page-scroll">
      <PageHeader
        title="Teams"
        description="Organize agents into teams for routing escalations. Team assignment is used by the AI agent when escalating conversations."
        action={
          canWrite ? (
            <button type="button" className="btn btn-primary" onClick={() => setShowCreate(true)}>
              <IconPlus size={16} />
              Create Team
            </button>
          ) : undefined
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
        <EmptyState message="No teams yet. Create one to start routing escalations." />
      )}

      <div className="grid-2 mb-6">
        {(teams.data ?? []).map((t) => {
          const roster = membersForTeam(t.id, users.data ?? []);
          const preview = roster.slice(0, 3);
          const overflow = Math.max(0, (t.member_count ?? roster.length) - preview.length);
          return (
            <button
              key={t.id}
              type="button"
              className="card"
              style={{
                textAlign: "left",
                cursor: "pointer",
                width: "100%",
                color: "inherit",
                font: "inherit",
              }}
              onClick={() => {
                setSelectedTeamId(t.id);
                setEditing(false);
                setSaveMsg(null);
                setSaveErr(null);
              }}
            >
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
                <span className="badge-count green">{t.member_count ?? roster.length} members</span>
              </div>
              {t.description && (
                <p className="text-sm text-muted" style={{ margin: "0 0 0.75rem" }}>{t.description}</p>
              )}
              <div className="flex items-center gap-2">
                {preview.length === 0 ? (
                  <span className="text-sm text-muted">No members yet</span>
                ) : (
                  <>
                    <div className="flex" style={{ marginLeft: 4 }}>
                      {preview.map((m, i) => (
                        <div key={m.id} style={{ marginLeft: i === 0 ? 0 : -8 }}>
                          <Avatar name={m.full_name} size="sm" />
                        </div>
                      ))}
                    </div>
                    {overflow > 0 && <span className="text-sm text-muted">+{overflow}</span>}
                  </>
                )}
              </div>
            </button>
          );
        })}
      </div>

      <h2 className="section-title">Organization Members</h2>
      <p className="form-hint mb-4">
        Open a team to add or remove members. Membership drives round-robin assignment and team notifications.
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
              <th>Teams</th>
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
                  <div className="flex gap-2" style={{ flexWrap: "wrap" }}>
                    {(u.teams ?? []).length === 0 ? (
                      <span className="text-sm text-muted">—</span>
                    ) : (
                      (u.teams ?? []).map((t) => (
                        <button
                          key={t.id}
                          type="button"
                          className="badge badge-normal"
                          style={{ cursor: "pointer", border: "none" }}
                          onClick={() => {
                            setSelectedTeamId(t.id);
                            setEditing(false);
                          }}
                        >
                          {t.name}
                        </button>
                      ))
                    )}
                  </div>
                </td>
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

      {selectedTeamId && (
        <Modal
          title={teamDetail.data?.name ?? "Team"}
          onClose={closeDetail}
          footer={
            <>
              {canWrite && (
                <button
                  type="button"
                  className="btn btn-danger"
                  disabled={removeTeam.isPending}
                  onClick={() => {
                    if (window.confirm("Delete this team? This cannot be undone.")) {
                      removeTeam.mutate(selectedTeamId);
                    }
                  }}
                >
                  <IconTrash size={14} />
                  Delete
                </button>
              )}
              <div style={{ flex: 1 }} />
              <button type="button" className="btn btn-ghost" onClick={closeDetail}>Close</button>
              {canWrite && !editing && (
                <button type="button" className="btn btn-primary" onClick={() => setEditing(true)}>
                  Edit
                </button>
              )}
              {canWrite && editing && (
                <button
                  type="submit"
                  form="edit-team-form"
                  className="btn btn-primary"
                  disabled={editSubmitting || update.isPending}
                >
                  Save
                </button>
              )}
            </>
          }
        >
          {teamDetail.isLoading && <LoadingState message="Loading team…" />}
          {teamDetail.isError && (
            <Alert type="error">
              {teamDetail.error instanceof ApiError ? teamDetail.error.message : "Failed to load team."}
            </Alert>
          )}
          {teamDetail.data && (
            <div style={{ display: "grid", gap: "1.25rem" }}>
              {editing ? (
                <form
                  id="edit-team-form"
                  onSubmit={handleEditSubmit((v) => update.mutate(v))}
                  style={{ display: "grid", gap: "1rem" }}
                >
                  <div className="form-field">
                    <label className="form-label" htmlFor="edit-team-name">Name *</label>
                    <input id="edit-team-name" className="form-input" {...registerEdit("name")} />
                    {editErrors.name && <span className="form-error">{editErrors.name.message}</span>}
                  </div>
                  <div className="form-field">
                    <label className="form-label" htmlFor="edit-team-desc">Description</label>
                    <input id="edit-team-desc" className="form-input" {...registerEdit("description")} />
                  </div>
                </form>
              ) : (
                <div>
                  <p className="text-sm text-muted" style={{ margin: 0 }}>
                    {teamDetail.data.description || "No description"}
                  </p>
                  <p className="text-sm text-muted" style={{ margin: "0.5rem 0 0" }}>
                    Created {formatDate(teamDetail.data.created_at)}
                  </p>
                </div>
              )}

              <div>
                <h3 className="section-title" style={{ marginBottom: "0.75rem" }}>Members</h3>
                {(teamDetail.data.members ?? []).length === 0 ? (
                  <p className="form-hint" style={{ marginBottom: "0.75rem" }}>
                    Round-robin and team notifications need at least one member.
                  </p>
                ) : (
                  <div className="table-wrap" style={{ marginBottom: "0.75rem" }}>
                    <table className="data-table">
                      <tbody>
                        {teamDetail.data.members.map((m) => (
                          <tr key={m.id}>
                            <td>
                              <div className="cell-with-avatar">
                                <Avatar name={m.full_name} size="sm" />
                                <div>
                                  <div className="cell-primary">{m.full_name}</div>
                                  <div className="text-sm text-muted">{m.email}</div>
                                </div>
                              </div>
                            </td>
                            <td style={{ width: 100, textAlign: "right" }}>
                              {canWrite && (
                                <button
                                  type="button"
                                  className="btn btn-ghost btn-sm"
                                  disabled={removeMember.isPending}
                                  onClick={() => removeMember.mutate(m.user_id)}
                                >
                                  Remove
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {canWrite && (
                  <div className="flex gap-2" style={{ alignItems: "flex-end" }}>
                    <div className="form-field" style={{ flex: 1, margin: 0 }}>
                      <label className="form-label" htmlFor="add-member">Add member</label>
                      <select
                        id="add-member"
                        className="form-select"
                        value={addUserId}
                        onChange={(e) => setAddUserId(e.target.value)}
                      >
                        <option value="">Select a user…</option>
                        {addableUsers.map((u) => (
                          <option key={u.id} value={u.id}>{u.full_name} ({u.email})</option>
                        ))}
                      </select>
                    </div>
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={!addUserId || addMember.isPending}
                      onClick={() => addMember.mutate(addUserId)}
                    >
                      Add
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}
        </Modal>
      )}
    </div>
  );
}
