import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/services/api/client";
import { Alert, LoadingState, PageHeader } from "@/components/ui";
import { IconChevronLeft } from "@/components/ui/icons";
import type { AutomationDetail } from "@/types";
import { ActionEditor, parseActions, serializeActions } from "./ActionEditor";
import { ConditionBuilder } from "./ConditionBuilder";
import { parseConditions, serializeConditions } from "./conditionUtils";
import {
  AUTOMATION_TRIGGERS,
  formatEnumLabel,
  getDefaultAction,
  type ActionFormState,
  type ConditionGroup,
} from "./types";

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
  const [enabled, setEnabled] = useState(true);
  const [conditions, setConditions] = useState<ConditionGroup | null>(null);
  const [conditionsUnsupported, setConditionsUnsupported] = useState(false);
  const [actions, setActions] = useState<ActionFormState[]>([getDefaultAction()]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (existing.data) {
      const a = existing.data;
      setName(a.name);
      setDescription(a.description ?? "");
      setTriggerType(a.trigger?.type ?? "MESSAGE_RECEIVED");
      setPriority(a.priority);
      setEnabled(a.enabled);
      const parsed = parseConditions(a.conditions);
      setConditions(parsed.group);
      setConditionsUnsupported(parsed.unsupported);
      setActions(parseActions(a.actions ?? []));
    }
  }, [existing.data]);

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        name: name.trim(),
        description: description.trim() || null,
        enabled,
        trigger: { type: triggerType },
        conditions: serializeConditions(conditions),
        actions: serializeActions(actions),
        priority,
      };
      if (isEdit) {
        return api(`/automations/${automationId}`, { method: "PATCH", body: JSON.stringify(body) });
      }
      return api("/automations", { method: "POST", body: JSON.stringify(body) });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["automations"] });
      if (isEdit) {
        void qc.invalidateQueries({ queryKey: ["automation", automationId] });
      }
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
          if (!actions.length) {
            setError("At least one action is required.");
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
              {AUTOMATION_TRIGGERS.map((t) => (
                <option key={t} value={t}>
                  {formatEnumLabel(t)}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="form-field">
          <label className="form-label" htmlFor="automation-enabled">
            <input
              id="automation-enabled"
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
              style={{ marginRight: "0.5rem" }}
            />
            Enabled
          </label>
          <span className="form-hint">Disabled automations will not run.</span>
        </div>

        <ConditionBuilder
          value={conditions}
          onChange={setConditions}
          unsupportedHint={conditionsUnsupported}
        />

        <ActionEditor value={actions} onChange={setActions} />

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
