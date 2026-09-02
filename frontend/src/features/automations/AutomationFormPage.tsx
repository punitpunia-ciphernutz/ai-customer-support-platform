import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/services/api/client";
import { Alert, LoadingState, PageHeader } from "@/components/ui";
import { IconChevronLeft } from "@/components/ui/icons";
import type { AutomationDetail } from "@/types";

const TRIGGERS = [
  "MESSAGE_RECEIVED",
  "CONVERSATION_CREATED",
  "CONVERSATION_ASSIGNED",
  "CONVERSATION_REOPENED",
  "CONVERSATION_CLOSED",
  "AI_ESCALATED",
  "MISSED_CHAT",
];

const ACTIONS = [
  "ASSIGN_TEAM",
  "ASSIGN_USER",
  "ASSIGN_ROUND_ROBIN",
  "SET_PRIORITY",
  "SET_STATUS",
  "ADD_TAG",
  "REMOVE_TAG",
  "CREATE_TICKET",
  "NOTIFY_TEAM",
  "NOTIFY_MANAGER",
  "NOTIFY_AGENT",
];

export function AutomationFormPage() {
  const { automationId } = useParams();
  const isEdit = Boolean(automationId);
  const navigate = useNavigate();
  const qc = useQueryClient();

  const existing = useQuery({
    queryKey: ["automation", automationId],
    queryFn: () => api<AutomationDetail>(`/automations/${automationId}`),
    enabled: isEdit,
  });

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [triggerType, setTriggerType] = useState("MESSAGE_RECEIVED");
  const [priority, setPriority] = useState(10);
  const [conditionsJson, setConditionsJson] = useState("");
  const [actionType, setActionType] = useState("SET_PRIORITY");
  const [actionValue, setActionValue] = useState("HIGH");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (existing.data) {
      const a = existing.data;
      setName(a.name);
      setDescription(a.description ?? "");
      setTriggerType(a.trigger?.type ?? "MESSAGE_RECEIVED");
      setPriority(a.priority);
      setConditionsJson(a.conditions ? JSON.stringify(a.conditions, null, 2) : "");
      const first = a.actions?.[0];
      if (first) {
        setActionType(first.type);
        setActionValue(first.value != null ? String(first.value) : "");
      }
    }
  }, [existing.data]);

  const save = useMutation({
    mutationFn: async () => {
      let conditions = null;
      if (conditionsJson.trim()) {
        conditions = JSON.parse(conditionsJson);
      }
      const body = {
        name: name.trim(),
        description: description.trim() || null,
        enabled: true,
        trigger: { type: triggerType },
        conditions,
        actions: [{ type: actionType, value: actionValue.trim() || undefined }],
        priority,
      };
      if (isEdit) {
        return api(`/automations/${automationId}`, { method: "PATCH", body: JSON.stringify(body) });
      }
      return api("/automations", { method: "POST", body: JSON.stringify(body) });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["automations"] });
      void navigate(isEdit ? `/automations/${automationId}` : "/automations");
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Save failed"),
  });

  if (isEdit && existing.isLoading) return <LoadingState message="Loading automation…" />;

  return (
    <div className="page-scroll">
      <Link to={isEdit ? `/automations/${automationId}` : "/automations"} className="back-link">
        <IconChevronLeft size={16} />
        {isEdit ? "Back to automation" : "Back to automations"}
      </Link>

      <PageHeader
        title={isEdit ? "Edit automation" : "New automation"}
        description="Define WHEN (trigger), IF (conditions), and THEN (actions)."
      />

      {error && <Alert type="error">{error}</Alert>}

      <form
        className="card"
        style={{ maxWidth: 640 }}
        onSubmit={(e) => {
          e.preventDefault();
          if (!name.trim()) {
            setError("Name is required.");
            return;
          }
          setError(null);
          void save.mutate();
        }}
      >
        <div className="form-field">
          <label className="form-label" htmlFor="automation-name">
            Name
          </label>
          <input
            id="automation-name"
            className="form-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Route Billing Conversations"
            required
          />
        </div>

        <div className="form-field">
          <label className="form-label" htmlFor="automation-description">
            Description
          </label>
          <input
            id="automation-description"
            className="form-input"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Optional description"
          />
        </div>

        <div className="grid-2">
          <div className="form-field">
            <label className="form-label" htmlFor="automation-priority">
              Priority
            </label>
            <input
              id="automation-priority"
              className="form-input"
              type="number"
              min={0}
              value={priority}
              onChange={(e) => setPriority(Number(e.target.value))}
            />
            <span className="form-hint">Higher priority runs first</span>
          </div>

          <div className="form-field">
            <label className="form-label" htmlFor="automation-trigger">
              WHEN — trigger
            </label>
            <select
              id="automation-trigger"
              className="form-select"
              value={triggerType}
              onChange={(e) => setTriggerType(e.target.value)}
            >
              {TRIGGERS.map((t) => (
                <option key={t} value={t}>
                  {t.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="form-field">
          <label className="form-label" htmlFor="automation-conditions">
            IF — conditions (JSON, optional)
          </label>
          <textarea
            id="automation-conditions"
            className="form-textarea"
            rows={6}
            value={conditionsJson}
            onChange={(e) => setConditionsJson(e.target.value)}
            placeholder='{"logic":"AND","conditions":[{"field":"intent","operator":"EQUALS","value":"BILLING"}]}'
          />
          <span className="form-hint">Leave empty to always run when the trigger fires.</span>
        </div>

        <div className="grid-2">
          <div className="form-field">
            <label className="form-label" htmlFor="automation-action">
              THEN — action
            </label>
            <select
              id="automation-action"
              className="form-select"
              value={actionType}
              onChange={(e) => setActionType(e.target.value)}
            >
              {ACTIONS.map((t) => (
                <option key={t} value={t}>
                  {t.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>

          <div className="form-field">
            <label className="form-label" htmlFor="automation-action-value">
              Action value
            </label>
            <input
              id="automation-action-value"
              className="form-input"
              value={actionValue}
              onChange={(e) => setActionValue(e.target.value)}
              placeholder="Team name, priority, tag, …"
            />
          </div>
        </div>

        <div className="flex items-center gap-2 mt-4">
          <button type="submit" className="btn btn-primary" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save automation"}
          </button>
          <Link to={isEdit ? `/automations/${automationId}` : "/automations"} className="btn btn-secondary">
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}
