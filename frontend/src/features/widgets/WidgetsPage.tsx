import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, ApiError } from "@/services/api/client";
import { Alert, LoadingState, PageHeader } from "@/components/ui";
import { SettingsSubNav } from "@/components/shared/SettingsSubNav";
import { cn } from "@/utils/cn";
import type { ChatWidget } from "@/features/widgets/types";

export function WidgetsPage() {
  const qc = useQueryClient();
  const widgets = useQuery({
    queryKey: ["widgets"],
    queryFn: () => api<ChatWidget[]>("/widgets"),
  });

  const create = useMutation({
    mutationFn: () =>
      api<ChatWidget>("/widgets", {
        method: "POST",
        body: JSON.stringify({
          name: "New Chat Widget",
          status: "DRAFT",
          allowed_domains: [],
        }),
      }),
    onSuccess: (widget) => {
      void qc.invalidateQueries({ queryKey: ["widgets"] });
      window.location.assign(`/settings/widgets/${widget.id}`);
    },
  });

  if (widgets.isLoading) return <LoadingState message="Loading widgets…" />;
  if (widgets.isError) {
    return (
      <div className="page-scroll">
        <Alert type="error">
          {widgets.error instanceof ApiError ? widgets.error.message : "Failed to load widgets."}
        </Alert>
      </div>
    );
  }

  return (
    <div className="page-scroll">
      <PageHeader
        title="Settings"
        description="Create embeddable chat widgets for your websites. Conversations use the existing Web Chat channel and AI pipeline."
        action={
          <button
            type="button"
            className="btn btn-primary"
            disabled={create.isPending}
            onClick={() => create.mutate()}
          >
            {create.isPending ? "Creating…" : "New widget"}
          </button>
        }
      />
      <SettingsSubNav />

      {create.isError && (
        <Alert type="error">
          {create.error instanceof ApiError ? create.error.message : "Could not create widget."}
        </Alert>
      )}

      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Widget ID</th>
              <th>Status</th>
              <th>Domains</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(widgets.data ?? []).length === 0 && (
              <tr>
                <td colSpan={5} className="text-muted">
                  No widgets yet. Create one to get an embed snippet.
                </td>
              </tr>
            )}
            {(widgets.data ?? []).map((w) => (
              <tr key={w.id}>
                <td>{w.name}</td>
                <td>
                  <code>{w.public_id}</code>
                </td>
                <td>
                  <span
                    className={cn(
                      "badge",
                      w.status === "ACTIVE" ? "badge-open" : w.status === "DRAFT" ? "badge-pending" : "badge-closed"
                    )}
                  >
                    {w.status}
                  </span>
                </td>
                <td>{(w.allowed_domains ?? []).join(", ") || "—"}</td>
                <td>
                  <Link to={`/settings/widgets/${w.id}`} className="btn btn-ghost btn-sm">
                    Configure
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
