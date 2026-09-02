import type { AutomationSummary } from "@/types";

export function formatTriggerLabel(type: string | undefined): string {
  if (!type) return "—";
  return type
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatActionLabel(action: { type: string; value?: unknown }): string {
  const label = action.type.replace(/_/g, " ").toLowerCase();
  const value = action.value != null && action.value !== "" ? ` → ${String(action.value)}` : "";
  return `${label}${value}`;
}

export function summarizeConditions(conditions: Record<string, unknown> | null): string {
  if (!conditions) return "Always run";
  const logic = (conditions.logic as string) ?? "AND";
  const items = (conditions.conditions as { field?: string; operator?: string; value?: unknown }[]) ?? [];
  if (!items.length) return "Always run";
  const parts = items.map((c) => {
    const field = c.field ?? "?";
    const op = (c.operator ?? "EQUALS").replace(/_/g, " ").toLowerCase();
    const val = c.value != null ? String(c.value) : "";
    return `${field} ${op} ${val}`.trim();
  });
  return `${logic}: ${parts.join("; ")}`;
}

export function automationStats(automations: AutomationSummary[]) {
  const enabled = automations.filter((a) => a.enabled).length;
  const executions = automations.reduce((sum, a) => sum + a.execution_count, 0);
  return { total: automations.length, enabled, executions };
}
