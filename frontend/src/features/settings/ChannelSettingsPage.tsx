import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/services/api/client";
import { Alert, LoadingState, PageHeader } from "@/components/ui";
import { SettingsSubNav } from "@/components/shared/SettingsSubNav";
import { cn } from "@/utils/cn";
import type { AIMode, ChannelType } from "@/types";

const MODE_LABELS: Record<AIMode, string> = {
  DRAFT_ONLY: "Knowledge Base",
  SUGGEST: "Suggest Reply",
  AUTO_REPLY: "Autopilot",
};

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
  const aiConfig = useQuery({
    queryKey: ["ai-config"],
    queryFn: () => api<{ channel_overrides: { channel: string; mode: AIMode | null }[] }>("/ai/config"),
  });

  const patch = useMutation({
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
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["ai-config"] }),
  });

  if (channels.isLoading || aiConfig.isLoading) return <LoadingState message="Loading channels…" />;
  if (channels.isError || aiConfig.isError) {
    return (
      <div className="page-scroll">
        <Alert type="error">
          {channels.error instanceof ApiError
            ? channels.error.message
            : aiConfig.error instanceof ApiError
              ? aiConfig.error.message
              : "Failed to load channels."}
        </Alert>
      </div>
    );
  }

  return (
    <div className="page-scroll">
      <PageHeader title="Settings" description="Configure inbound and outbound channels and AI modes per channel." />
      <SettingsSubNav />

      <div className="table-wrap">
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
            {(channels.data ?? []).map((ch) => {
              const mode =
                aiConfig.data?.channel_overrides.find((o) => o.channel === ch.channel)?.mode ?? null;
              return (
                <tr key={ch.id}>
                  <td>{ch.channel.replace(/_/g, " ")}</td>
                  <td>
                    <span className={cn("badge", ch.enabled ? "badge-open" : "badge-closed")}>
                      {ch.enabled ? "Connected" : "Disabled"}
                    </span>
                  </td>
                  <td>{ch.provider ?? "—"}</td>
                  <td>
                    {ch.channel === "FORM" ? (
                      <span className="text-muted">Coming soon</span>
                    ) : (
                      <select
                        className="form-select"
                        value={mode ?? ""}
                        onChange={(e) =>
                          patchMode.mutate({ channel: ch.channel, mode: e.target.value as AIMode })
                        }
                        disabled={patchMode.isPending}
                      >
                        <option value="" disabled>
                          Select mode
                        </option>
                        {(Object.keys(MODE_LABELS) as AIMode[]).map((m) => (
                          <option key={m} value={m}>
                            {MODE_LABELS[m]}
                          </option>
                        ))}
                      </select>
                    )}
                  </td>
                  <td>
                    {ch.channel === "FORM" ? (
                      <span className="text-muted">Coming soon</span>
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
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
