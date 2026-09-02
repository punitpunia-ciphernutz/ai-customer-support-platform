import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, ApiError } from "@/services/api/client";
import { Alert, LoadingState, PageHeader } from "@/components/ui";
import type { AIMode, ChannelType } from "@/types";

type ChannelConfig = {
  id: string;
  channel: ChannelType;
  enabled: boolean;
  provider: string | null;
  settings: Record<string, unknown>;
};

type AIConfig = {
  channel_overrides: { channel: string; mode: AIMode | null }[];
};

const MODE_LABELS: Record<AIMode, string> = {
  DRAFT_ONLY: "Knowledge Base",
  SUGGEST: "Suggest Reply",
  AUTO_REPLY: "Autopilot",
};

export function ChannelsPage() {
  const qc = useQueryClient();
  const channels = useQuery({
    queryKey: ["channels"],
    queryFn: () => api<ChannelConfig[]>("/channels"),
  });
  const aiConfig = useQuery({
    queryKey: ["ai-config"],
    queryFn: () => api<AIConfig>("/ai/config"),
  });

  const patchChannel = useMutation({
    mutationFn: ({ channel, enabled }: { channel: ChannelType; enabled: boolean }) =>
      api<ChannelConfig>(`/channels/${channel}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled }),
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["channels"] }),
  });

  const patchMode = useMutation({
    mutationFn: ({ channel, mode }: { channel: string; mode: AIMode }) =>
      api("/ai/config", {
        method: "PATCH",
        body: JSON.stringify({ channel_overrides: [{ channel, mode }] }),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["ai-config"] });
    },
  });

  if (channels.isLoading || aiConfig.isLoading) return <LoadingState message="Loading channels…" />;
  if (channels.isError || aiConfig.isError) {
    return (
      <Alert type="error">
        {channels.error instanceof ApiError
          ? channels.error.message
          : aiConfig.error instanceof ApiError
            ? aiConfig.error.message
            : "Failed to load channels."}
      </Alert>
    );
  }

  const modeFor = (channel: string) =>
    aiConfig.data?.channel_overrides.find((o) => o.channel === channel)?.mode ?? null;

  return (
    <div className="page">
      <PageHeader
        title="Channels"
        description="Overview of connected support channels."
        action={
          <Link className="btn btn-secondary btn-sm" to="/settings/channels">
            Channel settings →
          </Link>
        }
      />

      <div className="card">
        <table className="data-table">
          <thead>
            <tr>
              <th>Channel</th>
              <th>Status</th>
              <th>Provider</th>
              <th>AI mode</th>
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
                    <select
                      value={modeFor(ch.channel) ?? ""}
                      onChange={(e) =>
                        patchMode.mutate({ channel: ch.channel, mode: e.target.value as AIMode })
                      }
                      disabled={patchMode.isPending}
                    >
                      <option value="" disabled>Select mode</option>
                      {(Object.keys(MODE_LABELS) as AIMode[]).map((mode) => (
                        <option key={mode} value={mode}>
                          {MODE_LABELS[mode]}
                        </option>
                      ))}
                    </select>
                  )}
                </td>
                <td>
                  {ch.channel === "FORM" ? (
                    <span className="text-muted">—</span>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => patchChannel.mutate({ channel: ch.channel, enabled: !ch.enabled })}
                      disabled={patchChannel.isPending}
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
