import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/services/api/client";
import { formatDate, formatCost, formatPercent, statusClass } from "@/utils/format";
import type {
  AIConfig,
  AIMode,
  AIRunDetail,
  AIRunSummary,
  AIUsageSummary,
  AITestResponse,
  IntentLabel,
  Team,
} from "@/types";
import { INTENT_LABELS } from "@/types";
import {
  Alert,
  EmptyState,
  LoadingState,
  PageHeader,
  StatCard,
} from "@/components/ui";
import { SettingsSubNav } from "@/components/shared/SettingsSubNav";
import { cn } from "@/utils/cn";

type SelectOption = { value: string; label: string };

function SelectMenu({
  id,
  value,
  options,
  onChange,
  disabled,
}: {
  id: string;
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const selected = options.find((o) => o.value === value);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="select-menu" ref={rootRef}>
      <button
        type="button"
        id={id}
        className="form-select select-menu-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="select-menu-value">{selected?.label ?? value}</span>
        <span className="select-menu-chevron" aria-hidden>
          ▾
        </span>
      </button>
      {open && (
        <ul className="select-menu-list" role="listbox" aria-labelledby={id}>
          {options.map((opt) => (
            <li key={opt.value}>
              <button
                type="button"
                role="option"
                aria-selected={opt.value === value}
                className={cn("select-menu-option", opt.value === value && "selected")}
                onClick={() => {
                  onChange(opt.value);
                  setOpen(false);
                }}
              >
                {opt.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const MODE_OPTIONS: SelectOption[] = [
  { value: "DRAFT_ONLY", label: "Knowledge Base — send when grounded, else escalate" },
  { value: "SUGGEST", label: "Suggest Reply — drafts for agents only" },
  { value: "AUTO_REPLY", label: "Autopilot — auto-send when confident" },
];

type SettingsDraft = {
  enabled: boolean;
  mode: AIMode;
  auto_reply_threshold: number;
  escalation_threshold: number;
  require_knowledge: boolean;
  escalate_if_unknown: boolean;
  multilingual_enabled: boolean;
  ai_response_timeout_seconds: number;
  llm_model: string;
  allowed_intents: string[] | null;
  restricted_intents: string[];
  intent_team_map: Record<string, string>;
  response_policy_enabled: boolean;
  soft_reply_greetings: boolean;
  ood_soft_refuse: boolean;
  ood_escalates: boolean;
  assistant_scope_summary: string;
  assistant_display_name: string;
};

function emptyTeamMap(): Record<string, string> {
  return Object.fromEntries(INTENT_LABELS.map((intent) => [intent, ""]));
}

function draftFromConfig(config: AIConfig): SettingsDraft {
  return {
    enabled: config.enabled,
    mode: config.mode,
    auto_reply_threshold: config.auto_reply_threshold,
    escalation_threshold: config.escalation_threshold,
    require_knowledge: config.require_knowledge ?? true,
    escalate_if_unknown: config.escalate_if_unknown ?? true,
    multilingual_enabled: config.multilingual_enabled ?? true,
    ai_response_timeout_seconds: config.ai_response_timeout_seconds ?? 60,
    llm_model: config.llm_model ?? "gemini-3.1-flash-lite",
    allowed_intents: config.allowed_intents,
    restricted_intents: config.restricted_intents ?? [],
    intent_team_map: { ...emptyTeamMap(), ...(config.intent_team_map ?? {}) },
    response_policy_enabled: config.response_policy_enabled ?? true,
    soft_reply_greetings: config.soft_reply_greetings ?? true,
    ood_soft_refuse: config.ood_soft_refuse ?? true,
    ood_escalates: config.ood_escalates ?? false,
    assistant_scope_summary:
      config.assistant_scope_summary ??
      "password resets, account access, billing questions, and other topics in our help center",
    assistant_display_name: config.assistant_display_name ?? "Support Assistant",
  };
}

function payloadFromDraft(draft: SettingsDraft): Partial<AIConfig> {
  const intent_team_map: Record<string, string> = {};
  for (const [intent, teamName] of Object.entries(draft.intent_team_map)) {
    if (teamName.trim()) intent_team_map[intent] = teamName.trim();
  }
  return {
    enabled: draft.enabled,
    mode: draft.mode,
    auto_reply_threshold: draft.auto_reply_threshold,
    escalation_threshold: draft.escalation_threshold,
    require_knowledge: draft.require_knowledge,
    escalate_if_unknown: draft.escalate_if_unknown,
    multilingual_enabled: draft.multilingual_enabled,
    ai_response_timeout_seconds: draft.ai_response_timeout_seconds,
    llm_model: draft.llm_model,
    allowed_intents: draft.allowed_intents,
    restricted_intents: draft.restricted_intents,
    intent_team_map,
    response_policy_enabled: draft.response_policy_enabled,
    soft_reply_greetings: draft.soft_reply_greetings,
    ood_soft_refuse: draft.ood_soft_refuse,
    ood_escalates: draft.ood_escalates,
    assistant_scope_summary: draft.assistant_scope_summary,
    assistant_display_name: draft.assistant_display_name,
  };
}

export function SettingsPage() {
  const qc = useQueryClient();
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [testMessage, setTestMessage] = useState("How do I reset my password?");
  const [testResult, setTestResult] = useState<AITestResponse | null>(null);
  const [testErr, setTestErr] = useState<string | null>(null);
  const [draft, setDraft] = useState<SettingsDraft | null>(null);

  const aiConfig = useQuery({
    queryKey: ["ai-config"],
    queryFn: () => api<AIConfig>("/ai/config"),
  });

  const aiRuns = useQuery({
    queryKey: ["ai-runs"],
    queryFn: () => api<AIRunSummary[]>("/ai/runs?limit=50"),
    refetchInterval: 10000,
  });

  const aiUsage = useQuery({
    queryKey: ["ai-usage"],
    queryFn: () => api<AIUsageSummary>("/ai/usage?days=30"),
  });

  const SHOW_INTENT_TEAM_ROUTING = false;

  const teams = useQuery({
    queryKey: ["teams"],
    queryFn: () => api<Team[]>("/teams"),
    enabled: SHOW_INTENT_TEAM_ROUTING,
  });

  const runDetail = useQuery({
    queryKey: ["ai-run", selectedRunId],
    queryFn: () => api<AIRunDetail>(`/ai/runs/${selectedRunId}`),
    enabled: !!selectedRunId,
  });

  const patchConfig = useMutation({
    mutationFn: (body: Partial<AIConfig>) =>
      api<AIConfig>("/ai/config", { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: (saved) => {
      setDraft(draftFromConfig(saved));
      setSaveMsg("Settings saved.");
      setSaveErr(null);
      void qc.invalidateQueries({ queryKey: ["ai-config"] });
    },
    onError: (e) => {
      setSaveErr(e instanceof ApiError ? e.message : "Failed to save settings.");
      setSaveMsg(null);
    },
  });

  const testAi = useMutation({
    mutationFn: () =>
      api<AITestResponse>("/ai/test", {
        method: "POST",
        body: JSON.stringify({ message: testMessage }),
      }),
    onSuccess: (data) => {
      setTestResult(data);
      setTestErr(null);
      void qc.invalidateQueries({ queryKey: ["ai-runs"] });
    },
    onError: (e) => {
      setTestErr(e instanceof ApiError ? e.message : "AI test failed.");
      setTestResult(null);
    },
  });

  const config = aiConfig.data;

  useEffect(() => {
    if (config) setDraft((current) => current ?? draftFromConfig(config));
  }, [config]);

  const dirty =
    !!draft &&
    !!config &&
    JSON.stringify(payloadFromDraft(draft)) !== JSON.stringify(payloadFromDraft(draftFromConfig(config)));

  const updateDraft = (patch: Partial<SettingsDraft>) => {
    setDraft((current) => (current ? { ...current, ...patch } : current));
    setSaveMsg(null);
  };

  const toggleIntent = (field: "allowed_intents" | "restricted_intents", intent: IntentLabel) => {
    if (!draft) return;
    const current = draft[field] ?? [];
    const next = current.includes(intent)
      ? current.filter((i) => i !== intent)
      : [...current, intent];
    updateDraft({ [field]: next });
  };

  const saveSettings = () => {
    if (!draft) return;
    patchConfig.mutate(payloadFromDraft(draft));
  };

  return (
    <div className="page-scroll">
      <PageHeader
        title="Settings"
        description="Configure AI support behavior, thresholds, intent routing, and review recent AI runs."
        action={
          draft ? (
            <button
              type="button"
              className="btn btn-primary"
              onClick={saveSettings}
              disabled={!dirty || patchConfig.isPending}
            >
              {patchConfig.isPending ? "Saving…" : "Save settings"}
            </button>
          ) : undefined
        }
      />
      <SettingsSubNav />

      {saveMsg && <Alert type="success">{saveMsg}</Alert>}
      {saveErr && <Alert type="error">{saveErr}</Alert>}

      {aiUsage.data && (
        <section className="grid-4 mb-6" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "1rem" }}>
          <StatCard
            value={formatCost(aiUsage.data.total_cost_usd)}
            label="AI cost (30 days)"
            sublabel={`${aiUsage.data.total_runs} runs`}
            color="green"
            icon={<span>$</span>}
          />
          <StatCard
            value={aiUsage.data.total_tokens.total.toLocaleString()}
            label="Total tokens"
            sublabel={`${aiUsage.data.total_tokens.input.toLocaleString()} in · ${aiUsage.data.total_tokens.output.toLocaleString()} out`}
            color="blue"
            icon={<span>T</span>}
          />
        </section>
      )}

      {aiConfig.isLoading && <LoadingState message="Loading AI configuration…" />}
      {aiConfig.isError && (
        <Alert type="error">
          {aiConfig.error instanceof ApiError
            ? aiConfig.error.message
            : "Failed to load AI configuration."}
        </Alert>
      )}

      {draft && (
        <>
          {/* Card 1: Core Engine & Thresholds */}
          <section className="card mb-6" style={{ padding: "1.5rem" }}>
            <h2 className="section-title">Core Engine &amp; Thresholds</h2>

            <div
              className="mb-4"
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                gap: "1rem",
                alignItems: "start",
              }}
            >
              <div className="form-field" style={{ margin: 0 }}>
                <span className="form-label">AI Support enabled</span>
                <label
                  className="flex items-center gap-2"
                  htmlFor="ai-enabled"
                  style={{
                    cursor: "pointer",
                    fontSize: "0.875rem",
                    minHeight: "2.5rem",
                    padding: "0.5625rem 0",
                  }}
                >
                  <input
                    id="ai-enabled"
                    type="checkbox"
                    checked={draft.enabled}
                    onChange={(e) => updateDraft({ enabled: e.target.checked })}
                    disabled={patchConfig.isPending}
                  />
                  {draft.enabled ? "On" : "Off"}
                </label>
                <span className="form-hint">Master switch for AI replies and drafts</span>
              </div>
              <div className="form-field" style={{ margin: 0 }}>
                <label className="form-label" htmlFor="ai-mode">Mode</label>
                <SelectMenu
                  id="ai-mode"
                  value={draft.mode}
                  options={MODE_OPTIONS}
                  onChange={(value) => updateDraft({ mode: value as AIMode })}
                  disabled={patchConfig.isPending}
                />
              </div>
              <div className="form-field" style={{ margin: 0 }}>
                <label className="form-label" htmlFor="ai-model">Model</label>
                <SelectMenu
                  id="ai-model"
                  value={draft.llm_model}
                  options={(() => {
                    const options = config?.available_llm_models?.length
                      ? config.available_llm_models.map((m) => ({ value: m.id, label: m.label }))
                      : [];
                    if (!options.some((m) => m.value === draft.llm_model)) {
                      options.unshift({ value: draft.llm_model, label: draft.llm_model });
                    }
                    return options;
                  })()}
                  onChange={(value) => updateDraft({ llm_model: value })}
                  disabled={patchConfig.isPending}
                />
                <span className="form-hint">Gemini model used for classification and replies</span>
              </div>
            </div>

            <div className="grid-2 mb-4">
              <div className="form-field" style={{ margin: 0 }}>
                <div className="flex justify-between items-center" style={{ marginBottom: "0.35rem" }}>
                  <label className="form-label" htmlFor="auto-threshold" style={{ margin: 0 }}>
                    Auto-reply Threshold
                  </label>
                  <span className="text-sm" style={{ fontWeight: 600 }}>
                    {formatPercent(draft.auto_reply_threshold)}
                  </span>
                </div>
                <input
                  id="auto-threshold"
                  type="range"
                  min={0}
                  max={1}
                  step={0.01}
                  value={draft.auto_reply_threshold}
                  onChange={(e) =>
                    updateDraft({ auto_reply_threshold: parseFloat(e.target.value) })
                  }
                  disabled={patchConfig.isPending}
                  style={{ width: "100%" }}
                />
                <span className="form-hint">Minimum confidence to auto-reply (0–1)</span>
              </div>
              <div className="form-field" style={{ margin: 0 }}>
                <div className="flex justify-between items-center" style={{ marginBottom: "0.35rem" }}>
                  <label className="form-label" htmlFor="esc-threshold" style={{ margin: 0 }}>
                    Escalation Threshold
                  </label>
                  <span className="text-sm" style={{ fontWeight: 600 }}>
                    {formatPercent(draft.escalation_threshold)}
                  </span>
                </div>
                <input
                  id="esc-threshold"
                  type="range"
                  min={0}
                  max={1}
                  step={0.01}
                  value={draft.escalation_threshold}
                  onChange={(e) =>
                    updateDraft({ escalation_threshold: parseFloat(e.target.value) })
                  }
                  disabled={patchConfig.isPending}
                  style={{ width: "100%" }}
                />
                <span className="form-hint">Below this confidence, escalate to human (0–1)</span>
              </div>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                gap: "1rem",
              }}
            >
              <label style={{ cursor: "pointer", fontSize: "0.875rem" }}>
                <span className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={draft.require_knowledge}
                    onChange={(e) => updateDraft({ require_knowledge: e.target.checked })}
                    disabled={patchConfig.isPending}
                  />
                  Require knowledge before answering
                </span>
                <span className="form-hint" style={{ display: "block", marginTop: "0.25rem", paddingLeft: "1.5rem" }}>
                  Only reply when grounded in the knowledge base
                </span>
              </label>
              <label style={{ cursor: "pointer", fontSize: "0.875rem" }}>
                <span className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={draft.escalate_if_unknown}
                    onChange={(e) => updateDraft({ escalate_if_unknown: e.target.checked })}
                    disabled={patchConfig.isPending}
                  />
                  Escalate if unknown
                </span>
                <span className="form-hint" style={{ display: "block", marginTop: "0.25rem", paddingLeft: "1.5rem" }}>
                  Hand off when the answer cannot be determined
                </span>
              </label>
              <label style={{ cursor: "pointer", fontSize: "0.875rem" }}>
                <span className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={draft.multilingual_enabled}
                    onChange={(e) => updateDraft({ multilingual_enabled: e.target.checked })}
                    disabled={patchConfig.isPending}
                  />
                  Multilingual responses
                </span>
                <span className="form-hint" style={{ display: "block", marginTop: "0.25rem", paddingLeft: "1.5rem" }}>
                  Reply in the customer&apos;s detected language
                </span>
              </label>
            </div>
          </section>

          {/* Card 2: Response Policy */}
          <section className="card mb-6" style={{ padding: "1.5rem" }}>
            <h2 className="section-title">Response Policy</h2>
            <p className="form-hint mb-4">
              Soft-reply greetings and soft-refuse out-of-domain / no-KB questions without tickets.
              Turn off to restore legacy escalate-only behavior for those cases.
            </p>

            <div className="grid-2 mb-4">
              <label style={{ cursor: "pointer", fontSize: "0.875rem" }}>
                <span className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={draft.response_policy_enabled}
                    onChange={(e) => updateDraft({ response_policy_enabled: e.target.checked })}
                    disabled={patchConfig.isPending}
                  />
                  Response policy enabled
                </span>
                <span className="form-hint" style={{ display: "block", marginTop: "0.25rem", paddingLeft: "1.5rem" }}>
                  Apply soft-reply and soft-refuse rules
                </span>
              </label>
              <label style={{ cursor: "pointer", fontSize: "0.875rem" }}>
                <span className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={draft.soft_reply_greetings}
                    onChange={(e) => updateDraft({ soft_reply_greetings: e.target.checked })}
                    disabled={patchConfig.isPending || !draft.response_policy_enabled}
                  />
                  Soft-reply greetings / identity
                </span>
                <span className="form-hint" style={{ display: "block", marginTop: "0.25rem", paddingLeft: "1.5rem" }}>
                  Answer greetings and identity questions lightly
                </span>
              </label>
              <label style={{ cursor: "pointer", fontSize: "0.875rem" }}>
                <span className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={draft.ood_soft_refuse}
                    onChange={(e) => updateDraft({ ood_soft_refuse: e.target.checked })}
                    disabled={patchConfig.isPending || !draft.response_policy_enabled}
                  />
                  Soft-refuse OOD / no-KB (no ticket)
                </span>
                <span className="form-hint" style={{ display: "block", marginTop: "0.25rem", paddingLeft: "1.5rem" }}>
                  Decline out-of-scope questions without opening a ticket
                </span>
              </label>
              <label style={{ cursor: "pointer", fontSize: "0.875rem" }}>
                <span className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={draft.ood_escalates}
                    onChange={(e) => updateDraft({ ood_escalates: e.target.checked })}
                    disabled={patchConfig.isPending || !draft.response_policy_enabled}
                  />
                  Escalate OOD / no-KB to ticket
                </span>
                <span className="form-hint" style={{ display: "block", marginTop: "0.25rem", paddingLeft: "1.5rem" }}>
                  Create a ticket for out-of-scope or ungrounded asks
                </span>
              </label>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 240px), 1fr))",
                gap: "1.5rem",
                alignItems: "start",
              }}
            >
              <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                <div
                  className="flex justify-between items-center"
                  style={{ minHeight: "1.25rem", marginBottom: "0.375rem" }}
                >
                  <label
                    htmlFor="assistant-name"
                    style={{
                      fontSize: "0.875rem",
                      fontWeight: 500,
                      color: "var(--text-secondary)",
                    }}
                  >
                    Assistant display name
                  </label>
                  <span aria-hidden style={{ visibility: "hidden", fontSize: "0.875rem", fontWeight: 600 }}>
                    —
                  </span>
                </div>
                <div
                  style={{
                    height: "3.75rem",
                    display: "flex",
                    alignItems: "center",
                  }}
                >
                  <input
                    id="assistant-name"
                    className="form-input"
                    value={draft.assistant_display_name}
                    onChange={(e) => updateDraft({ assistant_display_name: e.target.value })}
                    disabled={patchConfig.isPending}
                    style={{
                      height: "2.5rem",
                      boxSizing: "border-box",
                      padding: "0 0.75rem",
                      lineHeight: "1.25",
                      borderRadius: "var(--radius-sm)",
                    }}
                  />
                </div>
                <span
                  className="form-hint"
                  style={{ display: "block", marginTop: "0.375rem", minHeight: "2.25rem" }}
                >
                  Name shown on AI replies
                </span>
              </div>

              <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                <div
                  className="flex justify-between items-center"
                  style={{ minHeight: "1.25rem", marginBottom: "0.375rem" }}
                >
                  <label
                    htmlFor="assistant-scope"
                    style={{
                      fontSize: "0.875rem",
                      fontWeight: 500,
                      color: "var(--text-secondary)",
                    }}
                  >
                    Scope summary
                  </label>
                  <span aria-hidden style={{ visibility: "hidden", fontSize: "0.875rem", fontWeight: 600 }}>
                    —
                  </span>
                </div>
                <div style={{ height: "3.75rem" }}>
                  <textarea
                    id="assistant-scope"
                    className="form-textarea"
                    rows={2}
                    value={draft.assistant_scope_summary}
                    onChange={(e) => updateDraft({ assistant_scope_summary: e.target.value })}
                    disabled={patchConfig.isPending}
                    style={{
                      height: "100%",
                      boxSizing: "border-box",
                      padding: "0.5rem 0.75rem",
                      lineHeight: "1.35",
                      borderRadius: "var(--radius-sm)",
                      resize: "none",
                      overflowY: "auto",
                    }}
                  />
                </div>
                <span
                  className="form-hint"
                  style={{ display: "block", marginTop: "0.375rem", minHeight: "2.25rem" }}
                >
                  Shown in soft replies
                </span>
              </div>

              <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                <div
                  className="flex justify-between items-center"
                  style={{ minHeight: "1.25rem", marginBottom: "0.375rem" }}
                >
                  <label
                    htmlFor="ai-response-timeout"
                    style={{
                      fontSize: "0.875rem",
                      fontWeight: 500,
                      color: "var(--text-secondary)",
                    }}
                  >
                    Timeout
                  </label>
                  <span style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text)" }}>
                    {draft.ai_response_timeout_seconds}s
                  </span>
                </div>
                <div
                  style={{
                    height: "3.75rem",
                    display: "flex",
                    alignItems: "center",
                    boxSizing: "border-box",
                  }}
                >
                  <input
                    id="ai-response-timeout"
                    type="range"
                    min={15}
                    max={180}
                    step={5}
                    value={draft.ai_response_timeout_seconds}
                    onChange={(e) =>
                      updateDraft({ ai_response_timeout_seconds: parseInt(e.target.value, 10) })
                    }
                    disabled={patchConfig.isPending}
                    style={{ width: "100%", margin: 0 }}
                  />
                </div>
                <span
                  className="form-hint"
                  style={{ display: "block", marginTop: "0.375rem", minHeight: "2.25rem" }}
                >
                  Create a ticket if AI does not respond in time
                </span>
              </div>
            </div>
          </section>

          {/* Card 3: Intent Configuration */}
          <section className="card mb-6" style={{ padding: "1.5rem" }}>
            <h2 className="section-title">Intent Configuration</h2>
            <p className="form-hint mb-4">
              Allowed intents are processed by AI. Restricted intents always escalate.
              Click Save settings to apply changes.
            </p>

            <div className="grid-2 mb-4">
              <div>
                <h3 className="section-title">Allowed Intents</h3>
                <div className="chips mb-4">
                  {INTENT_LABELS.map((intent) => {
                    const active = (draft.allowed_intents ?? []).includes(intent);
                    return (
                      <button
                        key={`allowed-${intent}`}
                        type="button"
                        className={cn("chip", active && "active")}
                        onClick={() => toggleIntent("allowed_intents", intent)}
                        disabled={patchConfig.isPending}
                      >
                        {intent.replace(/_/g, " ")}
                      </button>
                    );
                  })}
                </div>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => updateDraft({ allowed_intents: null })}
                  disabled={patchConfig.isPending}
                >
                  Clear (allow all)
                </button>
              </div>

              <div>
                <h3 className="section-title">Restricted Intents</h3>
                <div className="chips mb-4">
                  {INTENT_LABELS.map((intent) => {
                    const active = draft.restricted_intents.includes(intent);
                    return (
                      <button
                        key={`restricted-${intent}`}
                        type="button"
                        className={cn("chip restricted", active && "active")}
                        onClick={() => toggleIntent("restricted_intents", intent)}
                        disabled={patchConfig.isPending}
                      >
                        {intent.replace(/_/g, " ")}
                      </button>
                    );
                  })}
                </div>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => updateDraft({ restricted_intents: [] })}
                  disabled={patchConfig.isPending}
                >
                  Clear restrictions
                </button>
              </div>
            </div>

            {SHOW_INTENT_TEAM_ROUTING && (
              <>
                <h3 className="section-title">Intent → Team Routing</h3>
                <p className="form-hint mb-4">
                  When AI escalates, the ticket is assigned to the selected team.
                  Unmapped intents go to Support. Automations are not changed.
                </p>
                {teams.isError && (
                  <Alert type="error">
                    {teams.error instanceof ApiError ? teams.error.message : "Failed to load teams."}
                  </Alert>
                )}
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
                    gap: "0.75rem 1.25rem",
                  }}
                >
                  {INTENT_LABELS.map((intent) => {
                    const selected = draft.intent_team_map[intent] ?? "";
                    const teamOptions: SelectOption[] = [
                      { value: "", label: "Default (Support)" },
                      ...(teams.data ?? []).map((team) => ({
                        value: team.name,
                        label: team.name,
                      })),
                    ];
                    if (selected && !teamOptions.some((opt) => opt.value === selected)) {
                      teamOptions.push({ value: selected, label: `${selected} (missing)` });
                    }
                    return (
                      <div key={intent} className="flex items-center gap-3">
                        <span className="text-sm text-muted" style={{ width: 130, flexShrink: 0 }}>
                          {intent.replace(/_/g, " ")}
                        </span>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <SelectMenu
                            id={`intent-team-${intent}`}
                            value={selected}
                            options={teamOptions}
                            onChange={(value) =>
                              updateDraft({
                                intent_team_map: { ...draft.intent_team_map, [intent]: value },
                              })
                            }
                            disabled={patchConfig.isPending || teams.isLoading}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </section>
        </>
      )}

      {/* Card 4: AI Test Console & Recent Runs */}
      <section className="card mb-6" style={{ padding: "1.5rem" }}>
        <h2 className="section-title">AI Test Console &amp; Recent Runs</h2>

        <div
          className="mb-6"
          style={{
            background: "var(--bg-panel)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-lg)",
            padding: "1.25rem",
          }}
        >
          <h3 className="section-title" style={{ marginBottom: "0.5rem" }}>Test sandbox</h3>
          <p className="form-hint mb-4">
            Run a synchronous AI test without Celery — useful for debugging retrieval and escalation.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!testMessage.trim()) return;
              testAi.mutate();
            }}
            style={{ display: "grid", gap: "0.75rem" }}
          >
            <textarea
              className="form-textarea"
              rows={3}
              value={testMessage}
              onChange={(e) => setTestMessage(e.target.value)}
              placeholder="Enter a test message…"
            />
            <div className="flex justify-between items-center" style={{ flexWrap: "wrap", gap: "0.75rem" }}>
              <span className="form-hint" style={{ margin: 0 }}>
                Uses the current saved AI configuration
              </span>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={testAi.isPending || !testMessage.trim()}
              >
                {testAi.isPending ? "Running…" : "Run Test"}
              </button>
            </div>
          </form>
          {testErr && (
            <div className="mt-4">
              <Alert type="error">{testErr}</Alert>
            </div>
          )}
          {testResult && (
            <div
              className="mt-4"
              style={{
                background: "var(--bg-card)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
                padding: "1rem",
              }}
            >
              <div className="flex items-center gap-3 mb-4" style={{ flexWrap: "wrap" }}>
                <span className={statusClass(testResult.decision.toLowerCase())}>
                  {testResult.decision.replace(/_/g, " ")}
                </span>
                <span className="text-sm text-muted">
                  {testResult.intent.replace(/_/g, " ")} · {formatPercent(testResult.confidence)}
                  {testResult.grounded ? " · Grounded" : ""}
                  {testResult.message_kind ? ` · ${testResult.message_kind.replace(/_/g, " ")}` : ""}
                  {testResult.policy_action ? ` · Policy ${testResult.policy_action.replace(/_/g, " ")}` : ""}
                </span>
              </div>
              <p style={{ margin: 0, lineHeight: 1.6 }}>{testResult.answer}</p>
              {testResult.escalation_required && testResult.escalation_reason && (
                <p className="form-hint mt-4">Escalation reason: {testResult.escalation_reason}</p>
              )}
              {testResult.sources.length > 0 && (
                <ul className="text-sm text-muted" style={{ margin: "0.75rem 0 0", paddingLeft: "1.25rem" }}>
                  {testResult.sources.map((s) => (
                    <li key={s.document_id}>{s.title}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        <h3 className="section-title">Recent AI Runs</h3>
        {aiRuns.isLoading && <LoadingState message="Loading AI runs…" />}
        {aiRuns.isError && (
          <Alert type="error">
            {aiRuns.error instanceof ApiError ? aiRuns.error.message : "Failed to load AI runs."}
          </Alert>
        )}
        {!aiRuns.isLoading && !aiRuns.data?.length && (
          <EmptyState message="No AI runs yet. Send a message in Web Chat to trigger the agent." />
        )}

        {(aiRuns.data?.length ?? 0) > 0 && (
          <div className="grid-2" style={{ alignItems: "start" }}>
            <div className="table-wrap card-flush">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Status</th>
                    <th>Type</th>
                    <th>Intent</th>
                    <th>Conf.</th>
                    <th>Latency</th>
                    <th>Cost</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {(aiRuns.data ?? []).map((run) => (
                    <tr
                      key={run.id}
                      className="table-row-clickable"
                      onClick={() => setSelectedRunId(run.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setSelectedRunId(run.id);
                        }
                      }}
                      tabIndex={0}
                      role="button"
                      aria-pressed={selectedRunId === run.id}
                      aria-label={`Select AI run ${run.id.slice(0, 8)}`}
                      style={
                        selectedRunId === run.id
                          ? { background: "var(--bg-elevated)" }
                          : undefined
                      }
                    >
                      <td>
                        <span className={statusClass(run.status.toLowerCase())}>{run.status}</span>
                        {run.error && (
                          <div className="form-error" style={{ fontSize: "0.75rem", marginTop: "0.25rem" }}>
                            {run.error}
                          </div>
                        )}
                      </td>
                      <td className="text-sm">{run.type}</td>
                      <td className="text-sm">
                        {run.intent ? run.intent.replace(/_/g, " ") : "—"}
                      </td>
                      <td className="text-sm">
                        {run.confidence != null ? formatPercent(run.confidence) : "—"}
                      </td>
                      <td className="text-sm">
                        {run.latency_ms != null ? `${run.latency_ms}ms` : "—"}
                      </td>
                      <td className="text-sm">
                        {run.estimated_cost_usd != null ? formatCost(run.estimated_cost_usd) : "—"}
                      </td>
                      <td className="text-sm text-muted">{formatDate(run.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {selectedRunId && (
              <div
                style={{
                  background: "var(--bg-panel)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-lg)",
                  padding: "1.25rem",
                }}
              >
                {runDetail.isLoading && <LoadingState message="Loading run details…" />}
                {runDetail.data && (
                  <>
                    <h3 style={{ margin: "0 0 1rem", fontSize: "1rem", fontWeight: 700 }}>
                      Run {runDetail.data.id.slice(0, 8)}…
                    </h3>
                    <dl className="meta-grid mb-4">
                      <div>
                        <dt>Status</dt>
                        <dd>
                          <span className={statusClass(runDetail.data.status.toLowerCase())}>
                            {runDetail.data.status}
                          </span>
                        </dd>
                      </div>
                      <div><dt>Type</dt><dd>{runDetail.data.type}</dd></div>
                      <div><dt>Model</dt><dd>{runDetail.data.model ?? "—"}</dd></div>
                      <div><dt>Graph</dt><dd>{runDetail.data.graph_version ?? "—"}</dd></div>
                      <div><dt>Intent</dt><dd>{runDetail.data.intent ?? "—"}</dd></div>
                      <div><dt>Confidence</dt><dd>{formatPercent(runDetail.data.confidence)}</dd></div>
                      {runDetail.data.grounding_score != null && (
                        <div>
                          <dt>Grounding</dt>
                          <dd>{formatPercent(runDetail.data.grounding_score)}</dd>
                        </div>
                      )}
                      {runDetail.data.decision && (
                        <div><dt>Decision</dt><dd>{runDetail.data.decision}</dd></div>
                      )}
                      <div><dt>Retrieval</dt><dd>{runDetail.data.retrieval_count ?? "—"}</dd></div>
                      <div>
                        <dt>Latency</dt>
                        <dd>
                          {runDetail.data.latency_ms != null
                            ? `${runDetail.data.latency_ms}ms`
                            : "—"}
                        </dd>
                      </div>
                      <div><dt>Cost</dt><dd>{formatCost(runDetail.data.estimated_cost_usd)}</dd></div>
                      {runDetail.data.token_usage && (
                        <div>
                          <dt>Tokens</dt>
                          <dd>
                            {Number(
                              runDetail.data.token_usage.input_tokens ??
                                runDetail.data.token_usage.prompt_tokens ??
                                0,
                            ).toLocaleString()}{" "}
                            in ·{" "}
                            {Number(
                              runDetail.data.token_usage.output_tokens ??
                                runDetail.data.token_usage.completion_tokens ??
                                0,
                            ).toLocaleString()}{" "}
                            out
                          </dd>
                        </div>
                      )}
                      <div><dt>Created</dt><dd>{formatDate(runDetail.data.created_at)}</dd></div>
                      {runDetail.data.error && (
                        <div>
                          <dt>Error</dt>
                          <dd className="form-error">{runDetail.data.error}</dd>
                        </div>
                      )}
                    </dl>
                    {runDetail.data.input && Object.keys(runDetail.data.input).length > 0 && (
                      <details>
                        <summary
                          className="text-sm text-muted"
                          style={{ cursor: "pointer", marginBottom: "0.5rem" }}
                        >
                          Input
                        </summary>
                        <pre
                          style={{
                            background: "var(--bg-input)",
                            border: "1px solid var(--border)",
                            borderRadius: 8,
                            padding: "0.75rem",
                            fontSize: "0.75rem",
                            overflow: "auto",
                            maxHeight: 200,
                          }}
                        >
                          {JSON.stringify(runDetail.data.input, null, 2)}
                        </pre>
                      </details>
                    )}
                    {runDetail.data.trace && runDetail.data.trace.length > 0 && (
                      <details style={{ marginTop: "0.75rem" }}>
                        <summary
                          className="text-sm text-muted"
                          style={{ cursor: "pointer", marginBottom: "0.5rem" }}
                        >
                          Trace
                        </summary>
                        <pre
                          style={{
                            background: "var(--bg-input)",
                            border: "1px solid var(--border)",
                            borderRadius: 8,
                            padding: "0.75rem",
                            fontSize: "0.75rem",
                            overflow: "auto",
                            maxHeight: 200,
                          }}
                        >
                          {JSON.stringify(runDetail.data.trace, null, 2)}
                        </pre>
                      </details>
                    )}
                    {runDetail.data.output && (
                      <details style={{ marginTop: "0.75rem" }}>
                        <summary
                          className="text-sm text-muted"
                          style={{ cursor: "pointer", marginBottom: "0.5rem" }}
                        >
                          Output
                        </summary>
                        <pre
                          style={{
                            background: "var(--bg-input)",
                            border: "1px solid var(--border)",
                            borderRadius: 8,
                            padding: "0.75rem",
                            fontSize: "0.75rem",
                            overflow: "auto",
                            maxHeight: 200,
                          }}
                        >
                          {JSON.stringify(runDetail.data.output, null, 2)}
                        </pre>
                      </details>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
