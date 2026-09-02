import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "@/services/api/client";
import { Alert, LoadingState, PageHeader } from "@/components/ui";
import type { AutomationDetail, AutomationExecution, AutomationExecutionDetail } from "@/types";

export function AutomationDetailPage() {
  const { automationId } = useParams();
  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(null);

  const automation = useQuery({
    queryKey: ["automation", automationId],
    queryFn: () => api<AutomationDetail>(`/automations/${automationId}`),
    enabled: Boolean(automationId),
  });
  const executions = useQuery({
    queryKey: ["automation-executions", automationId],
    queryFn: () => api<AutomationExecution[]>(`/automations/${automationId}/executions`),
    enabled: Boolean(automationId),
  });
  const executionDetail = useQuery({
    queryKey: ["automation-execution", selectedExecutionId],
    queryFn: () => api<AutomationExecutionDetail>(`/automation-executions/${selectedExecutionId}`),
    enabled: Boolean(selectedExecutionId),
  });

  if (automation.isLoading) return <LoadingState message="Loading automation…" />;
  if (automation.isError) {
    return <Alert type="error">{automation.error instanceof ApiError ? automation.error.message : "Not found"}</Alert>;
  }

  const a = automation.data!;

  return (
    <div className="page">
      <PageHeader
        title={a.name}
        description={a.description ?? undefined}
        action={
          <Link to={`/automations/${automationId}/edit`} className="btn btn-secondary">
            Edit
          </Link>
        }
      />
      <div className="card stack gap-md">
        <div>
          <strong>WHEN</strong> {a.trigger?.type ?? "—"}
        </div>
        <div>
          <strong>IF</strong>
          <pre className="code-block">{JSON.stringify(a.conditions, null, 2)}</pre>
        </div>
        <div>
          <strong>THEN</strong>
          <ul>
            {(a.actions ?? []).map((action, i) => (
              <li key={i}>
                → {action.type} {action.value ? String(action.value) : ""}
              </li>
            ))}
          </ul>
        </div>
        <div>Status: {a.enabled ? "Enabled" : "Disabled"}</div>
      </div>
      <div className="card">
        <h3>Execution history</h3>
        {executions.isLoading ? (
          <LoadingState message="Loading executions…" />
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Status</th>
                <th>Started</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(executions.data ?? []).map((e) => (
                <tr key={e.id}>
                  <td>{e.id.slice(0, 8)}</td>
                  <td>{e.status}</td>
                  <td>{new Date(e.started_at).toLocaleString()}</td>
                  <td>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => setSelectedExecutionId(e.id)}>
                      Steps
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {selectedExecutionId && (
        <div className="card stack gap-md">
          <h3>Execution steps</h3>
          {executionDetail.isLoading ? (
            <LoadingState message="Loading steps…" />
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Duration</th>
                  <th>Result / error</th>
                </tr>
              </thead>
              <tbody>
                {(executionDetail.data?.steps ?? []).map((step) => (
                  <tr key={step.id}>
                    <td>{step.step_type}</td>
                    <td>{step.status}</td>
                    <td>{step.duration_ms != null ? `${step.duration_ms}ms` : "—"}</td>
                    <td>
                      <pre className="code-block">{step.error ?? JSON.stringify(step.result, null, 2)}</pre>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
