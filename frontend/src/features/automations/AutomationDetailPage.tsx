import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/services/api/client";
import { formatDate } from "@/utils/format";
import { Alert, LoadingState, PageHeader } from "@/components/ui";
import { IconChevronLeft } from "@/components/ui/icons";
import { cn } from "@/utils/cn";
import type { AutomationDetail, AutomationExecution, AutomationExecutionDetail } from "@/types";
import { formatActionLabel, formatTriggerLabel, summarizeConditions } from "./utils";

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
    return (
      <div className="page-scroll">
        <Alert type="error">
          {automation.error instanceof ApiError ? automation.error.message : "Automation not found."}
        </Alert>
        <Link to="/automations" className="btn btn-secondary mt-4">
          Back to automations
        </Link>
      </div>
    );
  }

  const a = automation.data!;

  return (
    <div className="page-scroll">
      <Link to="/automations" className="back-link">
        <IconChevronLeft size={16} />
        Back to automations
      </Link>

      <PageHeader
        title={a.name}
        description={a.description ?? undefined}
        action={
          <div className="flex items-center gap-2">
            <span className={cn("badge", a.enabled ? "badge-open" : "badge-closed")}>
              {a.enabled ? "Enabled" : "Disabled"}
            </span>
            <Link to={`/automations/${automationId}/edit`} className="btn btn-secondary">
              Edit
            </Link>
          </div>
        }
      />

      <section className="card mb-6">
        <h2 className="section-title">Rule definition</h2>
        <dl className="meta-grid">
          <div>
            <dt>WHEN</dt>
            <dd>
              <span className="badge badge-normal">{formatTriggerLabel(a.trigger?.type)}</span>
            </dd>
          </div>
          <div>
            <dt>Priority</dt>
            <dd>{a.priority}</dd>
          </div>
          <div className="meta-grid-full">
            <dt>IF</dt>
            <dd>{summarizeConditions(a.conditions)}</dd>
          </div>
          <div className="meta-grid-full">
            <dt>THEN</dt>
            <dd>
              {(a.actions ?? []).length ? (
                <ul className="action-list">
                  {(a.actions ?? []).map((action, i) => (
                    <li key={i}>{formatActionLabel(action)}</li>
                  ))}
                </ul>
              ) : (
                "—"
              )}
            </dd>
          </div>
        </dl>
      </section>

      <section className="card mb-6">
        <h2 className="section-title">Execution history</h2>
        {executions.isLoading ? (
          <LoadingState message="Loading executions…" />
        ) : !(executions.data ?? []).length ? (
          <p className="form-hint">No executions yet.</p>
        ) : (
          <div className="table-wrap card-flush">
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Status</th>
                  <th>Started</th>
                  <th>Completed</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {(executions.data ?? []).map((e) => (
                  <tr key={e.id}>
                    <td className="mono">{e.id.slice(0, 8)}…</td>
                    <td>
                      <span className={cn("badge", e.status === "COMPLETED" ? "badge-completed" : e.status === "FAILED" ? "badge-failed" : "badge-running")}>
                        {e.status}
                      </span>
                    </td>
                    <td>{formatDate(e.started_at)}</td>
                    <td>{formatDate(e.completed_at)}</td>
                    <td>
                      <button
                        type="button"
                        className={cn("btn btn-sm", selectedExecutionId === e.id ? "btn-primary" : "btn-secondary")}
                        onClick={() => setSelectedExecutionId(e.id)}
                      >
                        Steps
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {selectedExecutionId && (
        <section className="card">
          <h2 className="section-title">Execution steps</h2>
          {executionDetail.isLoading ? (
            <LoadingState message="Loading steps…" />
          ) : !(executionDetail.data?.steps ?? []).length ? (
            <p className="form-hint">No steps recorded.</p>
          ) : (
            <div className="table-wrap card-flush">
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
                      <td>
                        <span className={cn("badge", step.status === "COMPLETED" ? "badge-completed" : step.status === "FAILED" ? "badge-failed" : "badge-running")}>
                          {step.status}
                        </span>
                      </td>
                      <td>{step.duration_ms != null ? `${step.duration_ms}ms` : "—"}</td>
                      <td>
                        <pre className="code-preview">
                          {step.error ?? JSON.stringify(step.result, null, 2) ?? "—"}
                        </pre>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
