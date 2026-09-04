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

      <section className="card mb-6">
        <h2 className="section-title">AI Support</h2>
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
            <div className="flex gap-4 mb-4" style={{ flexWrap: "wrap", alignItems: "flex-start" }}>
              <div className="form-field" style={{ margin: 0, minWidth: 180 }}>
                <span className="form-label">Enabled</span>
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
                  AI Support enabled
                </label>
              </div>
              <div className="form-field" style={{ margin: 0, width: 300, maxWidth: "100%" }}>
                <label className="form-label" htmlFor="ai-mode">Mode</label>
                <SelectMenu
                  id="ai-mode"
                  value={draft.mode}
                  options={MODE_OPTIONS}
                  onChange={(value) => updateDraft({ mode: value as AIMode })}
                  disabled={patchConfig.isPending}
                />
              </div>
              <div className="form-field" style={{ margin: 0, width: 280, maxWidth: "100%" }}>
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

            <div className="grid-2">
              <div className="form-field">
                <label className="form-label" htmlFor="auto-threshold">
                  Auto-reply threshold ({formatPercent(draft.auto_reply_threshold)})
                </label>
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
              <div className="form-field">
                <label className="form-label" htmlFor="esc-threshold">
                  Escalation threshold ({formatPercent(draft.escalation_threshold)})
                </label>
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

            <div className="grid-2 mb-4">
              <label className="flex items-center gap-2" style={{ cursor: "pointer", fontSize: "0.875rem" }}>
                <input
                  type="checkbox"
                  checked={draft.require_knowledge}
                  onChange={(e) => updateDraft({ require_knowledge: e.target.checked })}
                  disabled={patchConfig.isPending}
                />
                Require knowledge before answering
              </label>
              <label className="flex items-center gap-2" style={{ cursor: "pointer", fontSize: "0.875rem" }}>
                <input
                  type="checkbox"
                  checked={draft.escalate_if_unknown}
                  onChange={(e) => updateDraft({ escalate_if_unknown: e.target.checked })}
                  disabled={patchConfig.isPending}
                />
                Escalate if unknown
              </label>
              <label className="flex items-center gap-2" style={{ cursor: "pointer", fontSize: "0.875rem" }}>
                <input
                  type="checkbox"
                  checked={draft.multilingual_enabled}
                  onChange={(e) => updateDraft({ multilingual_enabled: e.target.checked })}
                  disabled={patchConfig.isPending}
                />
                Multilingual responses
              </label>
            </div>

            <h3 className="section-title" style={{ fontSize: "0.95rem", marginTop: "0.5rem" }}>
              Response Policy
            </h3>
            <p className="form-hint mb-4">
              Soft-reply greetings and soft-refuse out-of-domain / no-KB questions without tickets.
              Turn off to restore legacy escalate-only behavior for those cases.
            </p>
            <div className="grid-2 mb-4">
              <label className="flex items-center gap-2" style={{ cursor: "pointer", fontSize: "0.875rem" }}>
                <input
                  type="checkbox"
                  checked={draft.response_policy_enabled}
                  onChange={(e) => updateDraft({ response_policy_enabled: e.target.checked })}
                  disabled={patchConfig.isPending}
                />
                Response policy enabled
              </label>
              <label className="flex items-center gap-2" style={{ cursor: "pointer", fontSize: "0.875rem" }}>
                <input
                  type="checkbox"
                  checked={draft.soft_reply_greetings}
                  onChange={(e) => updateDraft({ soft_reply_greetings: e.target.checked })}
                  disabled={patchConfig.isPending || !draft.response_policy_enabled}
                />
                Soft-reply greetings / identity
              </label>
              <label className="flex items-center gap-2" style={{ cursor: "pointer", fontSize: "0.875rem" }}>
                <input
                  type="checkbox"
                  checked={draft.ood_soft_refuse}
                  onChange={(e) => updateDraft({ ood_soft_refuse: e.target.checked })}
                  disabled={patchConfig.isPending || !draft.response_policy_enabled}
                />
                Soft-refuse OOD / no-KB (no ticket)
              </label>
              <label className="flex items-center gap-2" style={{ cursor: "pointer", fontSize: "0.875rem" }}>
                <input
                  type="checkbox"
                  checked={draft.ood_escalates}
                  onChange={(e) => updateDraft({ ood_escalates: e.target.checked })}
                  disabled={patchConfig.isPending || !draft.response_policy_enabled}
                />
                Escalate OOD / no-KB to ticket
              </label>
            </div>
            <div className="grid-2 mb-4">
              <div className="form-field">
                <label className="form-label" htmlFor="assistant-name">
                  Assistant display name
                </label>
                <input
                  id="assistant-name"
                  className="form-input"
                  value={draft.assistant_display_name}
                  onChange={(e) => updateDraft({ assistant_display_name: e.target.value })}
                  disabled={patchConfig.isPending}
                />
              </div>
              <div className="form-field">
                <label className="form-label" htmlFor="assistant-scope">
                  Scope summary (soft replies)
                </label>
                <input
                  id="assistant-scope"
                  className="form-input"
                  value={draft.assistant_scope_summary}
                  onChange={(e) => updateDraft({ assistant_scope_summary: e.target.value })}
                  disabled={patchConfig.isPending}
                />
              </div>
            </div>

            <div className="form-field" style={{ maxWidth: 280 }}>
              <label className="form-label" htmlFor="ai-response-timeout">
                AI response timeout ({draft.ai_response_timeout_seconds}s)
              </label>
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
                style={{ width: "100%" }}
              />
              <span className="form-hint">Create a ticket if AI does not respond in time</span>
            </div>
          </>
        )}
      </section>

      <section className="card mb-6">
        <h2 className="section-title">AI Evaluation</h2>
        <p className="form-hint mb-4">Run the Day 4 baseline suite (25 cases, offline Echo LLM in dev).</p>
        <EvalRunButton />
      </section>

      {draft && (
        <section className="card mb-6">
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

          <h3 className="section-title">Intent → Team Routing</h3>
          <p className="form-hint mb-4">
            When AI escalates, the ticket is assigned to this team. Use an existing team name
            (e.g. Billing). Unmapped intents go to Support. Automations are not changed.
          </p>
          <div style={{ display: "grid", gap: "0.5rem", maxWidth: 520 }}>
            {INTENT_LABELS.map((intent) => (
              <div key={intent} className="flex items-center gap-3">
                <span className="text-sm text-muted" style={{ width: 140, flexShrink: 0 }}>
                  {intent.replace(/_/g, " ")}
                </span>
                <input
                  className="form-input"
                  placeholder="Team name (e.g. Billing)"
                  value={draft.intent_team_map[intent] ?? ""}
                  onChange={(e) =>
                    updateDraft({
                      intent_team_map: { ...draft.intent_team_map, [intent]: e.target.value },
                    })
                  }
                  disabled={patchConfig.isPending}
                />
              </div>
            ))}
          </div>
          <button
            type="button"
            className="btn btn-primary mt-4"
            onClick={saveSettings}
            disabled={!dirty || patchConfig.isPending}
          >
            {patchConfig.isPending ? "Saving…" : "Save settings"}
          </button>
        </section>
      )}

      <section className="card mb-6">
        <h2 className="section-title">AI Test Console</h2>
        <p className="form-hint mb-4">
          Run a synchronous AI test without Celery — useful for debugging retrieval and escalation.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!testMessage.trim()) return;
            testAi.mutate();
          }}
          style={{ display: "grid", gap: "0.75rem", maxWidth: 560 }}
        >
          <textarea
            className="form-textarea"
            rows={3}
            value={testMessage}
            onChange={(e) => setTestMessage(e.target.value)}
            placeholder="Enter a test message…"
          />
          <button type="submit" className="btn btn-primary" disabled={testAi.isPending || !testMessage.trim()} style={{ justifySelf: "start" }}>
            {testAi.isPending ? "Running…" : "Run Test"}
          </button>
        </form>
        {testErr && <div className="mt-4"><Alert type="error">{testErr}</Alert></div>}
        {testResult && (
          <div className="card mt-4" style={{ background: "var(--bg-panel)" }}>
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
      </section>

      <section>
        <h2 className="section-title">Recent AI Runs</h2>
        {aiRuns.isLoading && <LoadingState message="Loading AI runs…" />}
        {aiRuns.isError && (
          <Alert type="error">
            {aiRuns.error instanceof ApiError ? aiRuns.error.message : "Failed to load AI runs."}
          </Alert>
        )}
        {!aiRuns.isLoading && !aiRuns.data?.length && (
          <EmptyState message="No AI runs yet. Send a message in Web Chat to trigger the agent." />
        )}

        <div className="grid-2">
          <div className="table-wrap card-flush">
            {(aiRuns.data ?? []).map((run) => (
              <button
                key={run.id}
                type="button"
                className={cn("list-item", selectedRunId === run.id && "selected")}
                onClick={() => setSelectedRunId(run.id)}
              >
                <div className="flex justify-between items-center">
                  <span className={statusClass(run.status.toLowerCase())}>{run.status}</span>
                  <span className="text-sm text-muted">{run.type}</span>
                </div>
                <div className="list-item-meta">
                  {run.intent && <span>{run.intent.replace(/_/g, " ")}</span>}
                  {run.confidence != null && <span>{formatPercent(run.confidence)}</span>}
                  {run.estimated_cost_usd != null && <span>{formatCost(run.estimated_cost_usd)}</span>}
                  {run.latency_ms != null && <span>{run.latency_ms}ms</span>}
                  <span>{formatDate(run.created_at)}</span>
                </div>
                {run.error && <span className="form-error">{run.error}</span>}
              </button>
            ))}
          </div>

          {selectedRunId && (
            <div className="card">
              {runDetail.isLoading && <LoadingState message="Loading run details…" />}
              {runDetail.data && (
                <>
                  <h3 style={{ margin: "0 0 1rem", fontSize: "1rem", fontWeight: 700 }}>
                    Run {runDetail.data.id.slice(0, 8)}…
                  </h3>
                  <dl className="meta-grid mb-4">
                    <div><dt>Status</dt><dd><span className={statusClass(runDetail.data.status.toLowerCase())}>{runDetail.data.status}</span></dd></div>
                    <div><dt>Type</dt><dd>{runDetail.data.type}</dd></div>
                    <div><dt>Model</dt><dd>{runDetail.data.model ?? "—"}</dd></div>
                    <div><dt>Graph</dt><dd>{runDetail.data.graph_version ?? "—"}</dd></div>
                    <div><dt>Intent</dt><dd>{runDetail.data.intent ?? "—"}</dd></div>
                    <div><dt>Confidence</dt><dd>{formatPercent(runDetail.data.confidence)}</dd></div>
                    {runDetail.data.grounding_score != null && (
                      <div><dt>Grounding</dt><dd>{formatPercent(runDetail.data.grounding_score)}</dd></div>
                    )}
                    {runDetail.data.decision && (
                      <div><dt>Decision</dt><dd>{runDetail.data.decision}</dd></div>
                    )}
                    <div><dt>Retrieval</dt><dd>{runDetail.data.retrieval_count ?? "—"}</dd></div>
                    <div><dt>Latency</dt><dd>{runDetail.data.latency_ms != null ? `${runDetail.data.latency_ms}ms` : "—"}</dd></div>
                    <div><dt>Cost</dt><dd>{formatCost(runDetail.data.estimated_cost_usd)}</dd></div>
                    {runDetail.data.token_usage && (
                      <div>
                        <dt>Tokens</dt>
                        <dd>
                          {Number(runDetail.data.token_usage.input_tokens ?? runDetail.data.token_usage.prompt_tokens ?? 0).toLocaleString()} in ·{" "}
                          {Number(runDetail.data.token_usage.output_tokens ?? runDetail.data.token_usage.completion_tokens ?? 0).toLocaleString()} out
                        </dd>
                      </div>
                    )}
                    <div><dt>Created</dt><dd>{formatDate(runDetail.data.created_at)}</dd></div>
                    {runDetail.data.error && (
                      <div><dt>Error</dt><dd className="form-error">{runDetail.data.error}</dd></div>
                    )}
                  </dl>
                  {runDetail.data.input && Object.keys(runDetail.data.input).length > 0 && (
                    <details>
                      <summary className="text-sm text-muted" style={{ cursor: "pointer", marginBottom: "0.5rem" }}>Input</summary>
                      <pre style={{ background: "var(--bg-input)", border: "1px solid var(--border)", borderRadius: 8, padding: "0.75rem", fontSize: "0.75rem", overflow: "auto", maxHeight: 200 }}>{JSON.stringify(runDetail.data.input, null, 2)}</pre>
                    </details>
                  )}
                  {runDetail.data.trace && runDetail.data.trace.length > 0 && (
                    <details style={{ marginTop: "0.75rem" }}>
                      <summary className="text-sm text-muted" style={{ cursor: "pointer", marginBottom: "0.5rem" }}>Trace</summary>
                      <pre style={{ background: "var(--bg-input)", border: "1px solid var(--border)", borderRadius: 8, padding: "0.75rem", fontSize: "0.75rem", overflow: "auto", maxHeight: 200 }}>{JSON.stringify(runDetail.data.trace, null, 2)}</pre>
                    </details>
                  )}
                  {runDetail.data.output && (
                    <details style={{ marginTop: "0.75rem" }}>
                      <summary className="text-sm text-muted" style={{ cursor: "pointer", marginBottom: "0.5rem" }}>Output</summary>
                      <pre style={{ background: "var(--bg-input)", border: "1px solid var(--border)", borderRadius: 8, padding: "0.75rem", fontSize: "0.75rem", overflow: "auto", maxHeight: 200 }}>{JSON.stringify(runDetail.data.output, null, 2)}</pre>
                    </details>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function EvalRunButton() {
  const [result, setResult] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true);
    setErr(null);
    try {
      const report = await api<{
        passed_cases: number;
        total_cases: number;
        intent_accuracy: number;
        escalation_accuracy: number;
      }>("/ai/evaluations/run", { method: "POST" });
      setResult(
        `Passed ${report.passed_cases}/${report.total_cases} · Intent ${Math.round(report.intent_accuracy * 100)}% · Escalation ${Math.round(report.escalation_accuracy * 100)}%`
      );
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Evaluation failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <button type="button" className="btn btn-primary btn-sm" onClick={() => void run()} disabled={loading}>
        {loading ? "Running…" : "Run evaluation suite"}
      </button>
      {result && <Alert type="success">{result}</Alert>}
      {err && <Alert type="error">{err}</Alert>}
    </div>
  );
}
