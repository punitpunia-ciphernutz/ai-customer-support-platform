import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, ApiError } from "@/services/api/client";
import { Alert, LoadingState, PageHeader } from "@/components/ui";
import { SettingsSubNav } from "@/components/shared/SettingsSubNav";
import { cn } from "@/utils/cn";
import type { ChatWidget } from "@/features/widgets/types";

type WidgetListView = "active" | "archive";

export function WidgetsPage() {
  const qc = useQueryClient();
  const [view, setView] = useState<WidgetListView>("active");

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

  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: ChatWidget["status"] }) =>
      api<ChatWidget>(`/widgets/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["widgets"] });
    },
  });

  const all = widgets.data ?? [];
  const activeWidgets = useMemo(
    () => all.filter((w) => w.status === "ACTIVE" || w.status === "DRAFT"),
    [all]
  );
  const archivedWidgets = useMemo(() => all.filter((w) => w.status === "INACTIVE"), [all]);
  const visible = view === "active" ? activeWidgets : archivedWidgets;

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
      {setStatus.isError && (
        <Alert type="error">
          {setStatus.error instanceof ApiError
            ? setStatus.error.message
            : "Could not update widget status."}
        </Alert>
      )}

      <div className="table-wrap">
        <div className="table-toolbar">
          <div className="chips">
            <button
              type="button"
              className={cn("chip", view === "active" && "active")}
              onClick={() => setView("active")}
            >
              Active ({activeWidgets.length})
            </button>
            <button
              type="button"
              className={cn("chip", view === "archive" && "active")}
              onClick={() => setView("archive")}
            >
              Archive ({archivedWidgets.length})
            </button>
          </div>
        </div>

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
            {visible.length === 0 && (
              <tr>
                <td colSpan={5} className="text-muted">
                  {view === "active"
                    ? "No active or draft widgets. Create one to get an embed snippet."
                    : "No archived widgets. Archive an inactive widget to hide it from the main list."}
                </td>
              </tr>
            )}
            {visible.map((w) => (
              <tr key={w.id}>
                <td>{w.name}</td>
                <td>
                  <code>{w.public_id}</code>
                </td>
                <td>
                  <span
                    className={cn(
                      "badge",
                      w.status === "ACTIVE"
                        ? "badge-open"
                        : w.status === "DRAFT"
                          ? "badge-pending"
                          : "badge-closed"
                    )}
                  >
                    {w.status === "INACTIVE" ? "ARCHIVED" : w.status}
                  </span>
                </td>
                <td>{(w.allowed_domains ?? []).join(", ") || "—"}</td>
                <td>
                  <div className="table-actions">
                    <Link to={`/settings/widgets/${w.id}`} className="btn btn-ghost btn-sm">
                      Configure
                    </Link>
                    {view === "active" ? (
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        disabled={setStatus.isPending}
                        onClick={() => {
                          if (
                            !confirm(
                              `Archive widget "${w.name}"?\n\nIt will move to Archive and stop working on websites. Chat history is kept.`
                            )
                          ) {
                            return;
                          }
                          setStatus.mutate({ id: w.id, status: "INACTIVE" });
                        }}
                      >
                        Archive
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        disabled={setStatus.isPending}
                        onClick={() => {
                          if (
                            !confirm(
                              `Restore widget "${w.name}" to the main list as Draft?\n\nYou can set it Active again from Configure when ready.`
                            )
                          ) {
                            return;
                          }
                          setStatus.mutate({ id: w.id, status: "DRAFT" });
                        }}
                      >
                        Restore
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
