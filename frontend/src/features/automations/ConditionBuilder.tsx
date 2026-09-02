import { INTENT_LABELS, PRIORITIES } from "@/types";
import {
  CHANNEL_TYPES,
  CONDITION_FIELDS,
  CONVERSATION_STATUSES,
  formatEnumLabel,
  getDefaultCondition,
  getFieldDef,
  MULTI_VALUE_OPERATORS,
  operatorNeedsValue,
  SENTIMENT_VALUES,
  type ConditionGroup,
  type ConditionLeaf,
  type ConditionOperator,
} from "./types";

type Props = {
  value: ConditionGroup | null;
  onChange: (value: ConditionGroup | null) => void;
  unsupportedHint?: boolean;
};

function ConditionValueInput({
  leaf,
  onChange,
}: {
  leaf: ConditionLeaf;
  onChange: (value: string | number | string[] | undefined) => void;
}) {
  const fieldDef = getFieldDef(leaf.field);
  const isMulti = MULTI_VALUE_OPERATORS.includes(leaf.operator);

  if (!operatorNeedsValue(leaf.operator)) {
    return <span className="form-hint">No value needed</span>;
  }

  if (fieldDef.valueType === "intent") {
    if (isMulti) {
      return (
        <input
          className="form-input"
          value={Array.isArray(leaf.value) ? leaf.value.join(", ") : String(leaf.value ?? "")}
          onChange={(e) =>
            onChange(
              e.target.value
                .split(",")
                .map((v) => v.trim())
                .filter(Boolean),
            )
          }
          placeholder="BILLING, REFUND"
        />
      );
    }
    return (
      <select
        className="form-select"
        value={String(leaf.value ?? INTENT_LABELS[0])}
        onChange={(e) => onChange(e.target.value)}
      >
        {INTENT_LABELS.map((intent) => (
          <option key={intent} value={intent}>
            {formatEnumLabel(intent)}
          </option>
        ))}
      </select>
    );
  }

  if (fieldDef.valueType === "sentiment") {
    if (isMulti) {
      return (
        <input
          className="form-input"
          value={Array.isArray(leaf.value) ? leaf.value.join(", ") : String(leaf.value ?? "")}
          onChange={(e) =>
            onChange(
              e.target.value
                .split(",")
                .map((v) => v.trim().toUpperCase())
                .filter(Boolean),
            )
          }
          placeholder="ANGRY, NEGATIVE"
        />
      );
    }
    return (
      <select
        className="form-select"
        value={String(leaf.value ?? SENTIMENT_VALUES[0])}
        onChange={(e) => onChange(e.target.value)}
      >
        {SENTIMENT_VALUES.map((sentiment) => (
          <option key={sentiment} value={sentiment}>
            {formatEnumLabel(sentiment)}
          </option>
        ))}
      </select>
    );
  }

  if (fieldDef.valueType === "channel") {
    if (isMulti) {
      return (
        <input
          className="form-input"
          value={Array.isArray(leaf.value) ? leaf.value.join(", ") : String(leaf.value ?? "")}
          onChange={(e) =>
            onChange(
              e.target.value
                .split(",")
                .map((v) => v.trim().toUpperCase())
                .filter(Boolean),
            )
          }
          placeholder="WEB_CHAT, EMAIL"
        />
      );
    }
    return (
      <select
        className="form-select"
        value={String(leaf.value ?? CHANNEL_TYPES[0])}
        onChange={(e) => onChange(e.target.value)}
      >
        {CHANNEL_TYPES.map((channel) => (
          <option key={channel} value={channel}>
            {formatEnumLabel(channel)}
          </option>
        ))}
      </select>
    );
  }

  if (fieldDef.valueType === "priority") {
    if (isMulti) {
      return (
        <input
          className="form-input"
          value={Array.isArray(leaf.value) ? leaf.value.join(", ") : String(leaf.value ?? "")}
          onChange={(e) =>
            onChange(
              e.target.value
                .split(",")
                .map((v) => v.trim().toUpperCase())
                .filter(Boolean),
            )
          }
          placeholder="HIGH, URGENT"
        />
      );
    }
    return (
      <select
        className="form-select"
        value={String(leaf.value ?? PRIORITIES[2])}
        onChange={(e) => onChange(e.target.value)}
      >
        {PRIORITIES.map((priority) => (
          <option key={priority} value={priority}>
            {formatEnumLabel(priority)}
          </option>
        ))}
      </select>
    );
  }

  if (fieldDef.valueType === "status") {
    if (isMulti) {
      return (
        <input
          className="form-input"
          value={Array.isArray(leaf.value) ? leaf.value.join(", ") : String(leaf.value ?? "")}
          onChange={(e) =>
            onChange(
              e.target.value
                .split(",")
                .map((v) => v.trim().toUpperCase())
                .filter(Boolean),
            )
          }
          placeholder="OPEN, CLOSED"
        />
      );
    }
    return (
      <select
        className="form-select"
        value={String(leaf.value ?? CONVERSATION_STATUSES[0])}
        onChange={(e) => onChange(e.target.value)}
      >
        {CONVERSATION_STATUSES.map((status) => (
          <option key={status} value={status}>
            {formatEnumLabel(status)}
          </option>
        ))}
      </select>
    );
  }

  if (fieldDef.valueType === "number") {
    return (
      <input
        className="form-input"
        type="number"
        min={0}
        max={1}
        step={0.01}
        value={leaf.value ?? 0.5}
        onChange={(e) => onChange(Number(e.target.value))}
        placeholder="0.5"
      />
    );
  }

  return (
    <input
      className="form-input"
      value={String(leaf.value ?? "")}
      onChange={(e) => onChange(e.target.value)}
      placeholder={isMulti ? "value1, value2" : "Value"}
    />
  );
}

function updateLeaf(group: ConditionGroup, index: number, patch: Partial<ConditionLeaf>): ConditionGroup {
  const conditions = group.conditions.map((leaf, i) => (i === index ? { ...leaf, ...patch } : leaf));
  return { ...group, conditions };
}

export function ConditionBuilder({ value, onChange, unsupportedHint }: Props) {
  const group = value ?? { logic: "AND" as const, conditions: [] };

  const setGroup = (next: ConditionGroup) => {
    onChange(next.conditions.length ? next : null);
  };

  const updateCondition = (index: number, patch: Partial<ConditionLeaf>) => {
    setGroup(updateLeaf(group, index, patch));
  };

  const addCondition = () => {
    setGroup({ ...group, conditions: [...group.conditions, getDefaultCondition()] });
  };

  const removeCondition = (index: number) => {
    setGroup({ ...group, conditions: group.conditions.filter((_, i) => i !== index) });
  };

  const handleFieldChange = (index: number, field: string) => {
    const fieldDef = getFieldDef(field);
    const leaf = group.conditions[index];
    const operator = fieldDef.operators.includes(leaf.operator) ? leaf.operator : fieldDef.operators[0];
    let nextValue: ConditionLeaf["value"];
    if (operatorNeedsValue(operator)) {
      if (fieldDef.valueType === "intent") nextValue = "BILLING";
      else if (fieldDef.valueType === "sentiment") nextValue = "ANGRY";
      else if (fieldDef.valueType === "channel") nextValue = "WEB_CHAT";
      else if (fieldDef.valueType === "priority") nextValue = "HIGH";
      else if (fieldDef.valueType === "status") nextValue = "OPEN";
      else if (fieldDef.valueType === "number") nextValue = 0.5;
      else nextValue = "";
    }
    updateCondition(index, { field, operator, value: nextValue });
  };

  const handleOperatorChange = (index: number, operator: ConditionOperator) => {
    const leaf = group.conditions[index];
    const patch: Partial<ConditionLeaf> = { operator };
    if (!operatorNeedsValue(operator)) {
      patch.value = undefined;
    } else if (leaf.value == null || leaf.value === "") {
      handleFieldChange(index, leaf.field);
      return;
    }
    updateCondition(index, patch);
  };

  return (
    <div className="form-field">
      <div className="flex items-center gap-2" style={{ justifyContent: "space-between" }}>
        <label className="form-label">IF — conditions (optional)</label>
        {group.conditions.length > 1 && (
          <select
            className="form-select"
            style={{ width: "auto", minWidth: 100 }}
            value={group.logic}
            onChange={(e) => setGroup({ ...group, logic: e.target.value as "AND" | "OR" })}
            aria-label="Condition logic"
          >
            <option value="AND">Match all (AND)</option>
            <option value="OR">Match any (OR)</option>
          </select>
        )}
      </div>

      {unsupportedHint && (
        <AlertHint message="Some nested condition groups could not be loaded in the builder. Saving will replace them with the conditions shown below." />
      )}

      {!group.conditions.length ? (
        <p className="form-hint" style={{ margin: 0 }}>
          No conditions — automation runs whenever the trigger fires.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {group.conditions.map((leaf, index) => {
            const fieldDef = getFieldDef(leaf.field);
            return (
              <div
                key={`${leaf.field}-${index}`}
                className="card"
                style={{ padding: "0.875rem", background: "var(--bg-input)" }}
              >
                <div className="grid-2" style={{ marginBottom: "0.75rem" }}>
                  <div className="form-field">
                    <label className="form-label">Field</label>
                    <select
                      className="form-select"
                      value={leaf.field}
                      onChange={(e) => handleFieldChange(index, e.target.value)}
                    >
                      {CONDITION_FIELDS.map((field) => (
                        <option key={field.id} value={field.id}>
                          {field.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="form-field">
                    <label className="form-label">Operator</label>
                    <select
                      className="form-select"
                      value={leaf.operator}
                      onChange={(e) => handleOperatorChange(index, e.target.value as ConditionOperator)}
                    >
                      {fieldDef.operators.map((operator) => (
                        <option key={operator} value={operator}>
                          {formatEnumLabel(operator)}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="form-field">
                  <label className="form-label">Value</label>
                  <ConditionValueInput
                    leaf={leaf}
                    onChange={(nextValue) => updateCondition(index, { value: nextValue })}
                  />
                </div>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm mt-4"
                  onClick={() => removeCondition(index)}
                >
                  Remove condition
                </button>
              </div>
            );
          })}
        </div>
      )}

      <button type="button" className="btn btn-secondary btn-sm" onClick={addCondition}>
        Add condition
      </button>
      <span className="form-hint">Leave empty to always run when the trigger fires.</span>
    </div>
  );
}

function AlertHint({ message }: { message: string }) {
  return (
    <p
      className="form-hint"
      style={{
        margin: 0,
        padding: "0.625rem 0.75rem",
        borderRadius: "var(--radius-sm)",
        background: "var(--warning-muted, rgba(234, 179, 8, 0.12))",
        color: "var(--warning, #ca8a04)",
      }}
    >
      {message}
    </p>
  );
}
