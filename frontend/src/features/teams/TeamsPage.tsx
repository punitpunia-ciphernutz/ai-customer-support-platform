import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/services/api/client";
import { formatDate } from "@/utils/format";
import type { RoleCatalogItem, RoleName, Team, TeamDetail, TeamMember, UserListItem } from "@/types";
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

const userSchema = z.object({
  full_name: z.string().min(1, "Name is required").max(255),
  email: z.string().email("Valid email required"),
  role: z.enum(["OWNER", "ADMIN", "MANAGER", "AGENT", "READ_ONLY"]),
  password: z.string().min(8, "Password must be at least 8 characters"),
});

type UserForm = z.infer<typeof userSchema>;

const editUserSchema = z.object({
  full_name: z.string().min(1, "Name is required").max(255),
  role: z.enum(["OWNER", "ADMIN", "MANAGER", "AGENT", "READ_ONLY"]),
});

type EditUserForm = z.infer<typeof editUserSchema>;

const ROLE_RANK: Record<RoleName, number> = {
  OWNER: 3,
  ADMIN: 3,
  MANAGER: 2,
  AGENT: 1,
  READ_ONLY: 1,
};

function membersForTeam(teamId: string, users: UserListItem[]): UserListItem[] {
  return users.filter((u) => (u.teams ?? []).some((t) => t.id === teamId));
}

function assignableRoles(actorRole: RoleName | undefined, catalog: RoleCatalogItem[]): RoleName[] {
  if (!actorRole) return [];
  const rank = ROLE_RANK[actorRole];
  return catalog.map((r) => r.name).filter((name) => ROLE_RANK[name] <= rank);
}

export function TeamsPage() {
  const qc = useQueryClient();
  const { user } = useAuth();
  const canWriteTeams = Boolean(user?.role.permissions.includes("teams.write"));
  const canWriteUsers = Boolean(user?.role.permissions.includes("users.write"));

  const [showCreate, setShowCreate] = useState(false);
  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [addUserId, setAddUserId] = useState("");
  const [showAddUser, setShowAddUser] = useState(false);
  const [editMember, setEditMember] = useState<UserListItem | null>(null);
  const [resetMember, setResetMember] = useState<UserListItem | null>(null);
  const [resetPassword, setResetPassword] = useState("");
  const [createdCreds, setCreatedCreds] = useState<{ email: string; password: string } | null>(null);
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

  const roles = useQuery({
    queryKey: ["roles"],
    queryFn: () => api<RoleCatalogItem[]>("/roles"),
    enabled: canWriteUsers,
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

  const {
    register: registerUser,
    handleSubmit: handleUserSubmit,
    reset: resetUser,
    formState: { errors: userErrors, isSubmitting: userSubmitting },
  } = useForm<UserForm>({
    resolver: zodResolver(userSchema),
    defaultValues: { role: "AGENT" },
  });

  const {
    register: registerEditUser,
    handleSubmit: handleEditUserSubmit,
    reset: resetEditUser,
    formState: { errors: editUserErrors, isSubmitting: editUserSubmitting },
  } = useForm<EditUserForm>({ resolver: zodResolver(editUserSchema) });

  useEffect(() => {
    if (teamDetail.data) {
      resetEdit({
        name: teamDetail.data.name,
        description: teamDetail.data.description ?? "",
      });
    }
  }, [teamDetail.data, resetEdit]);

  useEffect(() => {
    if (editMember) {
      resetEditUser({
        full_name: editMember.full_name,
        role: editMember.role.name,
      });
    }
  }, [editMember, resetEditUser]);

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

  const createUser = useMutation({
    mutationFn: (body: UserForm) =>
      api<UserListItem>("/users", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (_data, variables) => {
      resetUser({ full_name: "", email: "", role: "AGENT", password: "" });
      setShowAddUser(false);
      setCreatedCreds({ email: variables.email, password: variables.password });
      setSaveMsg("User created.");
      setSaveErr(null);
      invalidateAll();
    },
    onError: (e) => {
      setSaveErr(e instanceof ApiError ? e.message : "Failed to create user.");
      setSaveMsg(null);
    },
  });

  const updateUser = useMutation({
    mutationFn: (body: EditUserForm) =>
      api<UserListItem>(`/users/${editMember!.id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      setEditMember(null);
      setSaveMsg("User updated.");
      setSaveErr(null);
      invalidateAll();
    },
    onError: (e) => {
      setSaveErr(e instanceof ApiError ? e.message : "Failed to update user.");
      setSaveMsg(null);
    },
  });

  const toggleActive = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      api<UserListItem>(`/users/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active }),
      }),
    onSuccess: (_d, vars) => {
      setSaveMsg(vars.is_active ? "User activated." : "User deactivated.");
      setSaveErr(null);
      invalidateAll();
    },
    onError: (e) => {
      setSaveErr(e instanceof ApiError ? e.message : "Failed to update user status.");
      setSaveMsg(null);
    },
  });

  const doResetPassword = useMutation({
    mutationFn: ({ id, password }: { id: string; password: string }) =>
      api(`/users/${id}/reset-password`, {
        method: "POST",
        body: JSON.stringify({ password }),
      }),
    onSuccess: () => {
      setResetMember(null);
      setResetPassword("");
      setSaveMsg("Password reset.");
      setSaveErr(null);
    },
    onError: (e) => {
      setSaveErr(e instanceof ApiError ? e.message : "Failed to reset password.");
      setSaveMsg(null);
    },
  });

  const activeUsers = (users.data ?? []).filter((u) => u.is_active).length;

  const addableUsers = useMemo(() => {
    const memberIds = new Set((teamDetail.data?.members ?? []).map((m) => m.user_id));
    return (users.data ?? []).filter((u) => u.is_active && !memberIds.has(u.id));
  }, [teamDetail.data?.members, users.data]);

  const roleOptions = useMemo(
    () => assignableRoles(user?.role.name, roles.data ?? []),
    [user?.role.name, roles.data],
  );

  const closeDetail = () => {
    setSelectedTeamId(null);
    setEditing(false);
    setAddUserId("");
  };

  const canManageRow = (target: UserListItem) => {
    if (!canWriteUsers || !user) return false;
    return ROLE_RANK[user.role.name] >= ROLE_RANK[target.role.name];
  };

  return (
    <div className="page-scroll">
      <PageHeader
        title="Teams"
        description="Organize agents into teams for routing escalations. Team assignment is used by the AI agent when escalating conversations."
        action={
          canWriteTeams ? (
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
      {createdCreds && (
        <Alert type="success">
          User created. Share these credentials once: <strong>{createdCreds.email}</strong> /{" "}
          <strong>{createdCreds.password}</strong>
          <button type="button" className="btn btn-ghost btn-sm" style={{ marginLeft: 8 }} onClick={() => setCreatedCreds(null)}>
            Dismiss
          </button>
        </Alert>
      )}

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

      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="section-title" style={{ marginBottom: 4 }}>Organization Members</h2>
          <p className="form-hint" style={{ margin: 0 }}>
            Open a team to manage roster. {canWriteUsers ? "Add users, change roles, or deactivate accounts here." : "Team membership drives round-robin and notifications."}
          </p>
        </div>
        {canWriteUsers && (
          <button type="button" className="btn btn-primary" onClick={() => setShowAddUser(true)}>
            <IconPlus size={16} />
            Add User
          </button>
        )}
      </div>

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
              <th>Role</th>
              <th>Teams</th>
              <th>Status</th>
              {canWriteUsers && <th>Actions</th>}
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
                  <span className="badge badge-normal">{u.role?.name ?? "—"}</span>
                </td>
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
                {canWriteUsers && (
                  <td>
                    {canManageRow(u) ? (
                      <div className="flex gap-2" style={{ flexWrap: "wrap" }}>
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setEditMember(u)}>
                          Edit
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          disabled={toggleActive.isPending || u.id === user?.id}
                          onClick={() => toggleActive.mutate({ id: u.id, is_active: !u.is_active })}
                        >
                          {u.is_active ? "Deactivate" : "Activate"}
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => {
                            setResetMember(u);
                            setResetPassword("");
                          }}
                        >
                          Reset password
                        </button>
                      </div>
                    ) : (
                      <span className="text-sm text-muted">—</span>
                    )}
                  </td>
                )}
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

      {showAddUser && (
        <Modal
          title="Add User"
          onClose={() => setShowAddUser(false)}
          footer={
            <>
              <button type="button" className="btn btn-ghost" onClick={() => setShowAddUser(false)}>Cancel</button>
              <button
                type="submit"
                form="create-user-form"
                className="btn btn-primary"
                disabled={userSubmitting || createUser.isPending}
              >
                Create User
              </button>
            </>
          }
        >
          <form
            id="create-user-form"
            onSubmit={handleUserSubmit((v) => createUser.mutate(v))}
            style={{ display: "grid", gap: "1rem" }}
          >
            <div className="form-field">
              <label className="form-label" htmlFor="user-name">Full name *</label>
              <input id="user-name" className="form-input" {...registerUser("full_name")} />
              {userErrors.full_name && <span className="form-error">{userErrors.full_name.message}</span>}
            </div>
            <div className="form-field">
              <label className="form-label" htmlFor="user-email">Email *</label>
              <input id="user-email" className="form-input" type="email" {...registerUser("email")} />
              {userErrors.email && <span className="form-error">{userErrors.email.message}</span>}
            </div>
            <div className="form-field">
              <label className="form-label" htmlFor="user-role">Role *</label>
              <select id="user-role" className="form-select" {...registerUser("role")}>
                {roleOptions.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
              {userErrors.role && <span className="form-error">{userErrors.role.message}</span>}
            </div>
            <div className="form-field">
              <label className="form-label" htmlFor="user-password">Temporary password *</label>
              <input id="user-password" className="form-input" type="text" autoComplete="new-password" {...registerUser("password")} />
              {userErrors.password && <span className="form-error">{userErrors.password.message}</span>}
              <p className="form-hint">Shown once after create — share securely with the new user.</p>
            </div>
          </form>
        </Modal>
      )}

      {editMember && (
        <Modal
          title={`Edit ${editMember.full_name}`}
          onClose={() => setEditMember(null)}
          footer={
            <>
              <button type="button" className="btn btn-ghost" onClick={() => setEditMember(null)}>Cancel</button>
              <button
                type="submit"
                form="edit-user-form"
                className="btn btn-primary"
                disabled={editUserSubmitting || updateUser.isPending}
              >
                Save
              </button>
            </>
          }
        >
          <form
            id="edit-user-form"
            onSubmit={handleEditUserSubmit((v) => updateUser.mutate(v))}
            style={{ display: "grid", gap: "1rem" }}
          >
            <div className="form-field">
              <label className="form-label" htmlFor="edit-user-name">Full name *</label>
              <input id="edit-user-name" className="form-input" {...registerEditUser("full_name")} />
              {editUserErrors.full_name && <span className="form-error">{editUserErrors.full_name.message}</span>}
            </div>
            <div className="form-field">
              <label className="form-label" htmlFor="edit-user-role">Role *</label>
              <select id="edit-user-role" className="form-select" {...registerEditUser("role")}>
                {roleOptions.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
              {editUserErrors.role && <span className="form-error">{editUserErrors.role.message}</span>}
            </div>
            <p className="form-hint">{editMember.email}</p>
          </form>
        </Modal>
      )}

      {resetMember && (
        <Modal
          title={`Reset password — ${resetMember.full_name}`}
          onClose={() => setResetMember(null)}
          footer={
            <>
              <button type="button" className="btn btn-ghost" onClick={() => setResetMember(null)}>Cancel</button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={resetPassword.length < 8 || doResetPassword.isPending}
                onClick={() => doResetPassword.mutate({ id: resetMember.id, password: resetPassword })}
              >
                Reset password
              </button>
            </>
          }
        >
          <div className="form-field">
            <label className="form-label" htmlFor="reset-password">New temporary password *</label>
            <input
              id="reset-password"
              className="form-input"
              type="text"
              value={resetPassword}
              onChange={(e) => setResetPassword(e.target.value)}
              minLength={8}
            />
            <p className="form-hint">Minimum 8 characters. Share securely with the user.</p>
          </div>
        </Modal>
      )}

      {selectedTeamId && (
        <Modal
          title={teamDetail.data?.name ?? "Team"}
          onClose={closeDetail}
          footer={
            <>
              {canWriteTeams && (
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
              {canWriteTeams && !editing && (
                <button type="button" className="btn btn-primary" onClick={() => setEditing(true)}>
                  Edit
                </button>
              )}
              {canWriteTeams && editing && (
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
                              {canWriteTeams && (
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

                {canWriteTeams && (
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
