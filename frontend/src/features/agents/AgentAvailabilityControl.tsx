import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/features/auth/AuthContext";
import { api } from "@/services/api/client";
import { IconChevronDown } from "@/components/ui/icons";
import { cn } from "@/utils/cn";
import type { AgentStatus } from "@/types";

const STATUS_OPTIONS: { value: AgentStatus; label: string; hint: string }[] = [
  { value: "ONLINE", label: "Online", hint: "Can receive auto-assignments" },
  { value: "AWAY", label: "Away", hint: "Skipped for new assignments" },
  { value: "OFFLINE", label: "Offline", hint: "Not available for work" },
];

type AvailabilityRow = {
  user_id: string;
  status: AgentStatus;
  is_online?: boolean;
};

export function AgentAvailabilityControl() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const availability = useQuery({
    queryKey: ["agent-availability"],
    queryFn: () => api<AvailabilityRow[]>("/agents/availability"),
  });

  const patch = useMutation({
    mutationFn: (next: AgentStatus) =>
      api<AvailabilityRow>("/agents/me/availability", {
        method: "PATCH",
        body: JSON.stringify({ status: next }),
      }),
    onMutate: async (next) => {
      if (!user) return;
      await qc.cancelQueries({ queryKey: ["agent-availability"] });
      const previous = qc.getQueryData<AvailabilityRow[]>(["agent-availability"]);
      qc.setQueryData<AvailabilityRow[]>(["agent-availability"], (rows = []) => {
        const existing = rows.find((r) => r.user_id === user.id);
        if (existing) {
          return rows.map((r) =>
            r.user_id === user.id
              ? { ...r, status: next, is_online: next === "ONLINE" }
              : r,
          );
        }
        return [...rows, { user_id: user.id, status: next, is_online: next === "ONLINE" }];
      });
      return { previous };
    },
    onError: (_err, _next, ctx) => {
      if (ctx?.previous) {
        qc.setQueryData(["agent-availability"], ctx.previous);
      }
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: ["agent-availability"] }),
  });

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

  if (!user) return null;

  const current =
    availability.data?.find((r) => r.user_id === user.id)?.status ?? "ONLINE";
  const statusKey = current.toLowerCase();
  const currentLabel = STATUS_OPTIONS.find((o) => o.value === current)?.label ?? "Online";
  const disabled = patch.isPending || availability.isLoading;

  const selectStatus = (next: AgentStatus) => {
    setOpen(false);
    if (next === current) return;
    patch.mutate(next);
  };

  return (
    <div className="availability-control" ref={rootRef}>
      <button
        type="button"
        className={cn(
          "availability-pill",
          `is-${statusKey}`,
          open && "is-open",
          patch.isPending && "is-pending",
        )}
        aria-label="Agent availability"
        aria-expanded={open}
        aria-haspopup="listbox"
        disabled={disabled}
        title="Online agents can receive automatic assignments for their teams. Away and Offline are skipped."
        onClick={() => setOpen((v) => !v)}
      >
        <span className={cn("status-dot", `status-${statusKey}`)} aria-hidden />
        <span className="availability-label">{currentLabel}</span>
        <IconChevronDown
          size={14}
          className={cn("availability-chevron", open && "is-open")}
          aria-hidden
        />
      </button>

      {open && (
        <div className="availability-menu" role="listbox" aria-label="Availability status">
          {STATUS_OPTIONS.map((option) => {
            const key = option.value.toLowerCase();
            const selected = option.value === current;
            return (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={selected}
                className={cn("availability-option", `is-${key}`, selected && "is-selected")}
                onClick={() => selectStatus(option.value)}
              >
                <span className={cn("status-dot", `status-${key}`)} aria-hidden />
                <span className="availability-option-copy">
                  <span className="availability-option-label">{option.label}</span>
                  <span className="availability-option-hint">{option.hint}</span>
                </span>
              </button>
            );
          })}
        </div>
      )}

      {patch.isError && (
        <span className="availability-error" role="alert">
          Couldn’t update status
        </span>
      )}
    </div>
  );
}
