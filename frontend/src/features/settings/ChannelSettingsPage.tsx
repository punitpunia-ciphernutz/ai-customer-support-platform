import { useEffect, useState } from "react";
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

type AutoReplyDraft = {
  enabled: boolean;
  subject: string;
  body: string;
};

const DEFAULT_SUBJECT = "We received your message";
const DEFAULT_BODY =
  "Hi {{customer_name}},\n\nThanks for contacting us. We've received your email and will get back to you soon.\n\n— Support";

function readAutoReply(settings: Record<string, unknown> | undefined): AutoReplyDraft {
  return {
    enabled: Boolean(settings?.email_auto_reply_enabled),
    subject: String(settings?.email_auto_reply_subject ?? DEFAULT_SUBJECT),
    body: String(settings?.email_auto_reply_body ?? DEFAULT_BODY),
  };
}

export function ChannelSettingsPage() {
  const qc = useQueryClient();
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const [autoReply, setAutoReply] = useState<AutoReplyDraft>({
    enabled: false,
    subject: DEFAULT_SUBJECT,
    body: DEFAULT_BODY,
  });

  const channels = useQuery({
    queryKey: ["channels"],
    queryFn: () => api<ChannelConfig[]>("/channels"),
  });
  const aiConfig = useQuery({
    queryKey: ["ai-config"],
    queryFn: () => api<{ channel_overrides: { channel: string; mode: AIMode | null }[] }>("/ai/config"),
  });

  const emailChannel = (channels.data ?? []).find((ch) => ch.channel === "EMAIL");

  useEffect(() => {
    if (emailChannel) {
      setAutoReply(readAutoReply(emailChannel.settings));
    }
  }, [emailChannel]);

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

  const saveAutoReply = useMutation({
    mutationFn: (draft: AutoReplyDraft) =>
      api<ChannelConfig>("/channels/EMAIL", {
        method: "PATCH",
        body: JSON.stringify({
          settings: {
            email_auto_reply_enabled: draft.enabled,
            email_auto_reply_subject: draft.subject,
            email_auto_reply_body: draft.body,
          },
        }),
      }),
    onSuccess: () => {
      setSaveMsg("Email auto-responder saved.");
      setSaveErr(null);
      void qc.invalidateQueries({ queryKey: ["channels"] });
    },
    onError: (e) => {
      setSaveErr(e instanceof ApiError ? e.message : "Failed to save auto-responder.");
      setSaveMsg(null);
    },
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

      {saveMsg && <Alert type="success">{saveMsg}</Alert>}
      {saveErr && <Alert type="error">{saveErr}</Alert>}

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

      {emailChannel && (
        <section className="card mt-6">
          <h2 className="section-title">Email Auto-Responder</h2>
          <p className="form-hint mb-4">
            Send an immediate receipt email when a customer starts a new email conversation. Only the
            first message in a thread is acknowledged. Auto-submitted and bounce messages are ignored.
          </p>

          <label className="form-field form-field-inline">
            <input
              type="checkbox"
              checked={autoReply.enabled}
              onChange={(e) => setAutoReply((d) => ({ ...d, enabled: e.target.checked }))}
            />
            <span>Enable email auto-responder</span>
          </label>

          {autoReply.enabled && (
            <>
              <div className="form-field mt-4">
                <label className="form-label" htmlFor="auto-reply-subject">
                  Subject
                </label>
                <input
                  id="auto-reply-subject"
                  className="form-input"
                  value={autoReply.subject}
                  onChange={(e) => setAutoReply((d) => ({ ...d, subject: e.target.value }))}
                  placeholder={DEFAULT_SUBJECT}
                />
              </div>

              <div className="form-field">
                <label className="form-label" htmlFor="auto-reply-body">
                  Body
                </label>
                <textarea
                  id="auto-reply-body"
                  className="form-textarea"
                  rows={8}
                  value={autoReply.body}
                  onChange={(e) => setAutoReply((d) => ({ ...d, body: e.target.value }))}
                  placeholder={DEFAULT_BODY}
                />
                <p className="form-hint">
                  Placeholders: {"{{customer_name}}"}, {"{{customer_email}}"}, {"{{subject}}"},{" "}
                  {"{{conversation_id}}"}, {"{{ticket_id}}"}
                </p>
              </div>
            </>
          )}

          <div className="mt-4">
            <button
              type="button"
              className="btn btn-primary"
              disabled={saveAutoReply.isPending}
              onClick={() => saveAutoReply.mutate(autoReply)}
            >
              {saveAutoReply.isPending ? "Saving…" : "Save auto-responder"}
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
