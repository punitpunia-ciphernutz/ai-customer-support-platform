import { useQuery } from "@tanstack/react-query";
import { api } from "@/services/api/client";
import { PRIORITIES } from "@/types";
import type { Team, UserListItem } from "@/types";
import {
  actionNeedsValue,
  actionUsesConfig,
  AUTOMATION_ACTIONS,
  CONVERSATION_STATUSES,
  formatEnumLabel,
  getDefaultAction,
  PRIORITY_ACTIONS,
  TEAM_ACTIONS,
  USER_ACTIONS,
  type ActionFormState,
  type ActionType,
} from "./types";

type Props = {
  value: ActionFormState[];
  onChange: (value: ActionFormState[]) => void;
};

function ActionValueFields({
  action,
  teams,
  users,
  onChange,
}: {
  action: ActionFormState;
  teams: Team[];
  users: UserListItem[];
  onChange: (patch: Partial<ActionFormState>) => void;
}) {
  if (actionUsesConfig(action.type)) {
    const title = String(action.config?.title ?? "");
    return (
      <div className="form-field">
        <label className="form-label">Ticket title</label>
        <input
          className="form-input"
          value={title}
          onChange={(e) => onChange({ config: { ...action.config, title: e.target.value } })}
          placeholder="Missed Chat"
        />
      </div>
    );
  }

  if (!actionNeedsValue(action.type)) {
    return <span className="form-hint">No value needed for this action</span>;
  }

  if (TEAM_ACTIONS.includes(action.type)) {
    return (
      <div className="form-field">
        <label className="form-label">Team</label>
        <select
          className="form-select"
          value={action.value ?? ""}
          onChange={(e) => onChange({ value: e.target.value })}
        >
          <option value="">Select team…</option>
          {teams.map((team) => (
            <option key={team.id} value={team.name}>
              {team.name}
            </option>
          ))}
        </select>
      </div>
    );
  }

  if (USER_ACTIONS.includes(action.type)) {
    return (
      <div className="form-field">
        <label className="form-label">User</label>
        <select
          className="form-select"
          value={action.value ?? ""}
          onChange={(e) => onChange({ value: e.target.value })}
        >
          <option value="">Select user…</option>
          {users.map((user) => (
            <option key={user.id} value={user.id}>
              {user.full_name} ({user.email})
            </option>
          ))}
        </select>
      </div>
    );
  }

  if (PRIORITY_ACTIONS.includes(action.type)) {
    return (
      <div className="form-field">
        <label className="form-label">Priority</label>
        <select
          className="form-select"
          value={action.value ?? PRIORITIES[2]}
          onChange={(e) => onChange({ value: e.target.value })}
        >
          {PRIORITIES.map((priority) => (
            <option key={priority} value={priority}>
              {formatEnumLabel(priority)}
            </option>
          ))}
        </select>
      </div>
    );
  }

  if (action.type === "SET_STATUS") {
    return (
      <div className="form-field">
        <label className="form-label">Status</label>
        <select
          className="form-select"
          value={action.value ?? CONVERSATION_STATUSES[0]}
          onChange={(e) => onChange({ value: e.target.value })}
        >
          {CONVERSATION_STATUSES.map((status) => (
            <option key={status} value={status}>
              {formatEnumLabel(status)}
            </option>
          ))}
        </select>
      </div>
    );
  }

  return (
    <div className="form-field">
      <label className="form-label">Value</label>
      <input
        className="form-input"
        value={action.value ?? ""}
        onChange={(e) => onChange({ value: e.target.value })}
        placeholder={action.type === "ADD_TAG" || action.type === "REMOVE_TAG" ? "Tag name" : "Value"}
      />
    </div>
  );
}

function defaultValueForAction(type: ActionType): Partial<ActionFormState> {
  if (type === "SET_PRIORITY" || type === "SET_TICKET_PRIORITY") return { value: "HIGH" };
  if (type === "SET_STATUS") return { value: "OPEN" };
  if (type === "CREATE_TICKET") return { value: undefined, config: { title: "Automation ticket" } };
  if (!actionNeedsValue(type)) return { value: undefined, config: undefined };
  return { value: "", config: undefined };
}

export function ActionEditor({ value, onChange }: Props) {
  const teams = useQuery({
    queryKey: ["teams"],
    queryFn: () => api<Team[]>("/teams"),
  });
  const users = useQuery({
    queryKey: ["users"],
    queryFn: () => api<UserListItem[]>("/users"),
  });

  const updateAction = (index: number, patch: Partial<ActionFormState>) => {
    onChange(value.map((action, i) => (i === index ? { ...action, ...patch } : action)));
  };

  const handleTypeChange = (index: number, type: ActionType) => {
    updateAction(index, { type, ...defaultValueForAction(type) });
  };

  const addAction = () => {
    onChange([...value, getDefaultAction()]);
  };

  const removeAction = (index: number) => {
    onChange(value.filter((_, i) => i !== index));
  };

  return (
    <div className="form-field">
      <label className="form-label">THEN — actions</label>

      <div className="flex flex-col gap-3">
        {value.map((action, index) => (
          <div
            key={action.id}
            className="card"
            style={{ padding: "0.875rem", background: "var(--bg-input)" }}
          >
            <div className="form-field" style={{ marginBottom: "0.75rem" }}>
              <label className="form-label">Action type</label>
              <select
                className="form-select"
                value={action.type}
                onChange={(e) => handleTypeChange(index, e.target.value as ActionType)}
              >
                {AUTOMATION_ACTIONS.map((type) => (
                  <option key={type} value={type}>
                    {formatEnumLabel(type)}
                  </option>
                ))}
              </select>
            </div>

            <ActionValueFields
              action={action}
              teams={teams.data ?? []}
              users={users.data ?? []}
              onChange={(patch) => updateAction(index, patch)}
            />

            {value.length > 1 && (
              <button type="button" className="btn btn-secondary btn-sm mt-4" onClick={() => removeAction(index)}>
                Remove action
              </button>
            )}
          </div>
        ))}
      </div>

      <button type="button" className="btn btn-secondary btn-sm" onClick={addAction}>
        Add action
      </button>
    </div>
  );
}

export function serializeActions(actions: ActionFormState[]): Record<string, unknown>[] {
  return actions.map((action) => {
    const payload: Record<string, unknown> = { type: action.type };
    if (action.value != null && action.value !== "") {
      payload.value = action.value;
    }
    if (action.config && Object.keys(action.config).length > 0) {
      payload.config = action.config;
    }
    return payload;
  });
}

export function parseActions(raw: { type: string; value?: unknown; config?: Record<string, unknown> }[]): ActionFormState[] {
  if (!raw.length) return [getDefaultAction()];
  return raw.map((action) => ({
    id: crypto.randomUUID(),
    type: action.type as ActionType,
    value: action.value != null ? String(action.value) : undefined,
    config: action.config,
  }));
}
