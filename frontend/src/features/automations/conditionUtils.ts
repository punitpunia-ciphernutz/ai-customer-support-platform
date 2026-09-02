import type { ConditionGroup, ConditionLeaf, ConditionOperator } from "./types";
import { getFieldDef, MULTI_VALUE_OPERATORS, operatorNeedsValue } from "./types";

function isLeaf(item: Record<string, unknown>): item is ConditionLeaf & Record<string, unknown> {
  return typeof item.field === "string" && !("logic" in item) && !("conditions" in item);
}

function leafFromRecord(item: Record<string, unknown>): ConditionLeaf | null {
  if (!isLeaf(item)) return null;
  const operator = (item.operator as ConditionOperator) ?? "EQUALS";
  const leaf: ConditionLeaf = {
    field: item.field,
    operator,
  };
  if (operatorNeedsValue(operator) && item.value != null) {
    if (MULTI_VALUE_OPERATORS.includes(operator) && Array.isArray(item.value)) {
      leaf.value = item.value.map(String);
    } else if (typeof item.value === "number") {
      leaf.value = item.value;
    } else {
      leaf.value = String(item.value);
    }
  }
  return leaf;
}

/** Parse backend condition JSON into a flat builder state. Returns null if empty or unsupported nesting. */
export function parseConditions(raw: Record<string, unknown> | null | undefined): {
  group: ConditionGroup | null;
  unsupported: boolean;
} {
  if (!raw) return { group: null, unsupported: false };

  const logic = ((raw.logic as string) ?? "AND").toUpperCase() === "OR" ? "OR" : "AND";
  const items = (raw.conditions as Record<string, unknown>[]) ?? [];
  if (!items.length) return { group: null, unsupported: false };

  const leaves: ConditionLeaf[] = [];
  let unsupported = false;

  for (const item of items) {
    const leaf = leafFromRecord(item);
    if (leaf) {
      leaves.push(leaf);
      continue;
    }
    unsupported = true;
  }

  if (!leaves.length) return { group: null, unsupported };
  return { group: { logic, conditions: leaves }, unsupported };
}

export function serializeConditions(group: ConditionGroup | null): Record<string, unknown> | null {
  if (!group || !group.conditions.length) return null;

  const conditions = group.conditions.map((leaf) => {
    const entry: Record<string, unknown> = {
      field: leaf.field,
      operator: leaf.operator,
    };
    if (operatorNeedsValue(leaf.operator) && leaf.value != null && leaf.value !== "") {
      if (MULTI_VALUE_OPERATORS.includes(leaf.operator)) {
        entry.value = Array.isArray(leaf.value)
          ? leaf.value
          : String(leaf.value)
              .split(",")
              .map((v) => v.trim())
              .filter(Boolean);
      } else if (getFieldDef(leaf.field).valueType === "number") {
        entry.value = Number(leaf.value);
      } else {
        entry.value = leaf.value;
      }
    }
    return entry;
  });

  return { logic: group.logic, conditions };
}
