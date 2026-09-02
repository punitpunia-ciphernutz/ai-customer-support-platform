import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/features/auth/AuthContext";
import { api } from "@/services/api/client";
import type { AgentStatus } from "@/types";

const STATUS_LABELS: Record<AgentStatus, string> = {
  ONLINE: "Online",
  AWAY: "Away",
  OFFLINE: "Offline",
};

export function AgentAvailabilityControl() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const availability = useQuery({
    queryKey: ["agent-availability"],
    queryFn: () =>
      api<{ user_id: string; status: AgentStatus }[]>("/agents/availability"),
  });

  const patch = useMutation({
    mutationFn: (next: AgentStatus) =>
      api("/agents/me/availability", { method: "PATCH", body: JSON.stringify({ status: next }) }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["agent-availability"] }),
  });

  if (!user) return null;

  const current =
    availability.data?.find((r) => r.user_id === user.id)?.status ?? "ONLINE";

  return (
    <div className="availability-control">
      <span className={`status-dot status-${current.toLowerCase()}`} />
      <select
        className="input input-sm"
        value={current}
        onChange={(e) => patch.mutate(e.target.value as AgentStatus)}
        aria-label="Agent availability"
      >
        {(Object.keys(STATUS_LABELS) as AgentStatus[]).map((s) => (
          <option key={s} value={s}>
            {STATUS_LABELS[s]}
          </option>
        ))}
      </select>
    </div>
  );
}
