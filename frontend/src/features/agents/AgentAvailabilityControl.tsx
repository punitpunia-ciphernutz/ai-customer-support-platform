import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/features/auth/AuthContext";
import { api } from "@/services/api/client";
import type { AgentStatus } from "@/types";

const STATUS_LABELS: Record<AgentStatus, string> = {
  ONLINE: "Online",
  AWAY: "Away",
  OFFLINE: "Offline",
};

type AvailabilityRow = {
  user_id: string;
  status: AgentStatus;
  is_online?: boolean;
};

export function AgentAvailabilityControl() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const availability = useQuery({
    queryKey: ["agent-availability"],
    queryFn: () => api<AvailabilityRow[]>("/agents/availability"),
  });

  const patch = useMutation({
    mutationFn: (next: AgentStatus) =>
      api<AvailabilityRow>("/agents/me/availability", {
        method: "PATCH",
        body: JSON.stringify({ status: next }),
      }),
    onMutate: async (next) => {
      if (!user) return;
      await qc.cancelQueries({ queryKey: ["agent-availability"] });
      const previous = qc.getQueryData<AvailabilityRow[]>(["agent-availability"]);
      qc.setQueryData<AvailabilityRow[]>(["agent-availability"], (rows = []) => {
        const existing = rows.find((r) => r.user_id === user.id);
        if (existing) {
          return rows.map((r) =>
            r.user_id === user.id
              ? { ...r, status: next, is_online: next === "ONLINE" }
              : r,
          );
        }
        return [...rows, { user_id: user.id, status: next, is_online: next === "ONLINE" }];
      });
      return { previous };
    },
    onError: (_err, _next, ctx) => {
      if (ctx?.previous) {
        qc.setQueryData(["agent-availability"], ctx.previous);
      }
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: ["agent-availability"] }),
  });

  if (!user) return null;

  const current =
    availability.data?.find((r) => r.user_id === user.id)?.status ?? "ONLINE";

  return (
    <div className="availability-control">
      <span className={`status-dot status-${current.toLowerCase()}`} aria-hidden />
      <select
        className="input input-sm"
        value={current}
        disabled={patch.isPending || availability.isLoading}
        onChange={(e) => patch.mutate(e.target.value as AgentStatus)}
        aria-label="Agent availability"
      >
        {(Object.keys(STATUS_LABELS) as AgentStatus[]).map((s) => (
          <option key={s} value={s}>
            {STATUS_LABELS[s]}
          </option>
        ))}
      </select>
      {patch.isError && (
        <span className="form-hint" role="alert" style={{ color: "var(--danger)", margin: 0 }}>
          Couldn’t update status
        </span>
      )}
    </div>
  );
}
