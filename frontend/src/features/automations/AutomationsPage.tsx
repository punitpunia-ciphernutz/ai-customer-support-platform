import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/services/api/client";
import { Alert, EmptyState, LoadingState, PageHeader, StatCard } from "@/components/ui";
import { IconAutomation, IconPlus, IconSearch } from "@/components/ui/icons";
import { cn } from "@/utils/cn";
import type { AutomationSummary } from "@/types";
import { automationStats, formatTriggerLabel, summarizeConditions } from "./utils";

type StatusFilter = "all" | "enabled" | "disabled";

export function AutomationsPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["automations"],
    queryFn: () => api<AutomationSummary[]>("/automations"),
  });

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      api(`/automations/${id}/${enabled ? "enable" : "disable"}`, { method: "POST" }),
    onSuccess: () => {
      setActionError(null);
      void qc.invalidateQueries({ queryKey: ["automations"] });
    },
    onError: (e) => setActionError(e instanceof ApiError ? e.message : "Failed to update automation."),
  });

  const filtered = useMemo(() => {
    let list = [...(data ?? [])].sort((a, b) => b.priority - a.priority || a.name.localeCompare(b.name));
    if (statusFilter === "enabled") list = list.filter((row) => row.enabled);
    if (statusFilter === "disabled") list = list.filter((row) => !row.enabled);
    const q = search.trim().toLowerCase();
    if (q) {
      list = list.filter(
        (row) =>
          row.name.toLowerCase().includes(q) ||
          formatTriggerLabel(row.trigger?.type).toLowerCase().includes(q) ||
          summarizeConditions(row.conditions).toLowerCase().includes(q)
      );
    }
    return list;
  }, [data, search, statusFilter]);

  const stats = automationStats(data ?? []);

  if (isLoading) return <LoadingState message="Loading automations…" />;

  return (
    <div className="page-scroll">
      <PageHeader
        title="Automations"
        description="Deterministic routing and actions triggered by support events."
        action={
          <Link to="/automations/new" className="btn btn-primary">
            <IconPlus size={16} />
            New automation
          </Link>
        }
      />

      {isError && (
        <Alert type="error">
          {error instanceof ApiError ? error.message : "Failed to load automations."}
        </Alert>
      )}
      {actionError && <Alert type="error">{actionError}</Alert>}

      <section
        className="mb-6"
        style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "1rem" }}
      >
        <StatCard
          icon={<IconAutomation size={20} />}
          value={stats.total}
          label="Total automations"
          sublabel={`${stats.enabled} enabled`}
          color="green"
        />
        <StatCard
          icon={<span>▶</span>}
          value={stats.executions}
          label="Total executions"
          sublabel="All time"
          color="blue"
        />
      </section>

      <div className="table-wrap">
        <div className="table-toolbar">
          <div className="table-search">
            <IconSearch size={16} />
            <input
              className="form-input"
              placeholder="Search by name, trigger, or condition…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="chips">
            {(["all", "enabled", "disabled"] as const).map((value) => (
              <button
                key={value}
                type="button"
                className={cn("chip", statusFilter === value && "active")}
                onClick={() => setStatusFilter(value)}
              >
                {value === "all" ? "All" : value === "enabled" ? "Enabled" : "Disabled"}
              </button>
            ))}
          </div>
        </div>

        {!filtered.length ? (
          <EmptyState
            message={
              search || statusFilter !== "all"
                ? "No automations match your filters."
                : "No automations yet. Create one to route conversations automatically."
            }
            icon={<IconAutomation size={48} />}
          />
        ) : (
          <>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Trigger</th>
                  <th>Status</th>
                  <th>Priority</th>
                  <th>Executions</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((row) => (
                  <tr key={row.id} className="table-row-clickable">
                    <td>
                      <Link to={`/automations/${row.id}`} className="table-link">
                        <div className="table-link-title">{row.name}</div>
                        {row.description && <div className="table-link-sub">{row.description}</div>}
                        {!row.description && row.conditions && (
                          <div className="table-link-sub">{summarizeConditions(row.conditions)}</div>
                        )}
                      </Link>
                    </td>
                    <td>
                      <span className="badge badge-normal">{formatTriggerLabel(row.trigger?.type)}</span>
                    </td>
                    <td>
                      <span className={cn("badge", row.enabled ? "badge-open" : "badge-closed")}>
                        {row.enabled ? "ON" : "OFF"}
                      </span>
                    </td>
                    <td>{row.priority}</td>
                    <td>{row.execution_count}</td>
                    <td>
                      <div className="table-actions">
                        <Link to={`/automations/${row.id}`} className="btn btn-ghost btn-sm">
                          View
                        </Link>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          disabled={toggle.isPending}
                          onClick={() => toggle.mutate({ id: row.id, enabled: !row.enabled })}
                        >
                          {row.enabled ? "Disable" : "Enable"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="table-footer">
              <span>
                Showing {filtered.length} of {data?.length ?? 0} automations
              </span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
