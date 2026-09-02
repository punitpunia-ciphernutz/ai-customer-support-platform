import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, ApiError } from "@/services/api/client";
import { Alert, LoadingState, PageHeader } from "@/components/ui";
import type { AutomationSummary } from "@/types";

export function AutomationsPage() {
  const qc = useQueryClient();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["automations"],
    queryFn: () => api<AutomationSummary[]>("/automations"),
  });

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      api(`/automations/${id}/${enabled ? "enable" : "disable"}`, { method: "POST" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["automations"] }),
  });

  if (isLoading) return <LoadingState message="Loading automations…" />;
  if (isError) return <Alert type="error">{error instanceof ApiError ? error.message : "Failed to load automations."}</Alert>;

  return (
    <div className="page">
      <PageHeader
        title="Automations"
        description="Deterministic routing and actions triggered by support events."
        action={
          <Link to="/automations/new" className="btn btn-primary">
            New automation
          </Link>
        }
      />
      <div className="card">
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Status</th>
              <th>Priority</th>
              <th>Executions</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((row) => (
              <tr key={row.id}>
                <td>
                  <Link to={`/automations/${row.id}`}>{row.name}</Link>
                </td>
                <td>{row.enabled ? "ON" : "OFF"}</td>
                <td>{row.priority}</td>
                <td>{row.execution_count}</td>
                <td>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => toggle.mutate({ id: row.id, enabled: !row.enabled })}
                  >
                    {row.enabled ? "Disable" : "Enable"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
