import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, ApiError } from "@/services/api/client";
import { Alert, LoadingState, PageHeader } from "@/components/ui";
import type { ChannelType } from "@/types";

type ChannelConfig = {
  id: string;
  channel: ChannelType;
  enabled: boolean;
  provider: string | null;
  settings: Record<string, unknown>;
};

export function ChannelSettingsPage() {
  const qc = useQueryClient();
  const channels = useQuery({
    queryKey: ["channels"],
    queryFn: () => api<ChannelConfig[]>("/channels"),
  });

  const patch = useMutation({
    mutationFn: ({ channel, enabled }: { channel: ChannelType; enabled: boolean }) =>
      api<ChannelConfig>(`/channels/${channel}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled }),
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["channels"] }),
  });

  if (channels.isLoading) return <LoadingState message="Loading channels…" />;
  if (channels.isError) {
    return (
      <Alert type="error">
        {channels.error instanceof ApiError ? channels.error.message : "Failed to load channels."}
      </Alert>
    );
  }

  return (
    <div className="page">
      <PageHeader
        title="Channel settings"
        description="Configure inbound and outbound channels."
        action={<Link className="btn btn-secondary btn-sm" to="/settings">← Settings</Link>}
      />

      <div className="card">
        <table className="data-table">
          <thead>
            <tr>
              <th>Channel</th>
              <th>Status</th>
              <th>Provider</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {(channels.data ?? []).map((ch) => (
              <tr key={ch.id}>
                <td>{ch.channel.replace(/_/g, " ")}</td>
                <td>{ch.enabled ? "Connected" : "Disabled"}</td>
                <td>{ch.provider ?? "—"}</td>
                <td>
                  {ch.channel === "FORM" ? (
                    <span className="text-muted">Coming Soon</span>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => patch.mutate({ channel: ch.channel, enabled: !ch.enabled })}
                      disabled={patch.isPending}
                    >
                      {ch.enabled ? "Disable" : "Enable"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
