import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "@/services/api/client";
import { Alert, LoadingState, PageHeader } from "@/components/ui";
import type { AutomationDetail } from "@/types";

const TRIGGERS = [
  "MESSAGE_RECEIVED",
  "CONVERSATION_CREATED",
  "CONVERSATION_ASSIGNED",
  "CONVERSATION_REOPENED",
  "AI_ESCALATED",
  "MISSED_CHAT",
];

const ACTIONS = [
  "ASSIGN_TEAM",
  "SET_PRIORITY",
  "ADD_TAG",
  "NOTIFY_TEAM",
  "NOTIFY_MANAGER",
  "CREATE_TICKET",
  "SET_STATUS",
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
      const conditions = conditionsJson.trim() ? JSON.parse(conditionsJson) : null;
      const body = {
        name,
        description: description.trim() || null,
        enabled: true,
        trigger: { type: triggerType },
        conditions,
        actions: [{ type: actionType, value: actionValue || undefined }],
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
    <div className="page">
      <PageHeader
        title={isEdit ? "Edit automation" : "New automation"}
        description="Define WHEN (trigger), IF (conditions), and THEN (actions)."
      />
      {error && <Alert type="error">{error}</Alert>}
      <div className="card stack gap-md">
        <label>
          Name
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          Description
          <input className="input" value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <label>
          Priority
          <input
            className="input"
            type="number"
            value={priority}
            onChange={(e) => setPriority(Number(e.target.value))}
          />
        </label>
        <label>
          WHEN — trigger
          <select className="input" value={triggerType} onChange={(e) => setTriggerType(e.target.value)}>
            {TRIGGERS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label>
          IF — conditions (JSON, optional)
          <textarea
            className="input"
            rows={6}
            value={conditionsJson}
            onChange={(e) => setConditionsJson(e.target.value)}
            placeholder='{"logic":"AND","conditions":[{"field":"intent","operator":"EQUALS","value":"BILLING"}]}'
          />
        </label>
        <div className="stack gap-sm">
          <strong>THEN — action</strong>
          <select className="input" value={actionType} onChange={(e) => setActionType(e.target.value)}>
            {ACTIONS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <input
            className="input"
            value={actionValue}
            onChange={(e) => setActionValue(e.target.value)}
            placeholder="Action value (team name, priority, tag, …)"
          />
        </div>
        <div className="row gap-sm">
          <button type="button" className="btn btn-primary" onClick={() => void save.mutate()} disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save"}
          </button>
          <Link to={isEdit ? `/automations/${automationId}` : "/automations"} className="btn btn-secondary">
            Cancel
          </Link>
        </div>
      </div>
    </div>
  );
}
