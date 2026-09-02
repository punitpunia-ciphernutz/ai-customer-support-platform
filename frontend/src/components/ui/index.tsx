import { ReactNode } from "react";
import { cn } from "@/utils/cn";

const AVATAR_COLORS = [
  "#10b981", "#3b82f6", "#a855f7", "#f59e0b", "#ef4444",
  "#06b6d4", "#ec4899", "#8b5cf6", "#14b8a6", "#f97316",
];

function colorForName(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

export function Avatar({
  name,
  size = "md",
  className,
}: {
  name: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const sizeClass = size === "sm" ? "avatar-sm" : size === "lg" ? "avatar-lg" : "";
  return (
    <div
      className={cn("avatar", sizeClass, className)}
      style={{ background: colorForName(name) }}
      aria-hidden
    >
      {initials(name)}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  action,
}: {
  title: ReactNode;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <h1 className="page-title">{title}</h1>
        {description && <p className="page-desc">{description}</p>}
      </div>
      {action}
    </header>
  );
}

export function StatCard({
  icon,
  value,
  label,
  sublabel,
  color = "green",
}: {
  icon: ReactNode;
  value: string | number;
  label: string;
  sublabel?: string;
  color?: "green" | "purple" | "orange" | "blue";
}) {
  return (
    <div className="stat-card">
      <div className={cn("stat-icon", color)}>{icon}</div>
      <div>
        <div className="stat-value">{value}</div>
        <div className="stat-label">{label}</div>
        {sublabel && <div className="stat-sublabel">{sublabel}</div>}
      </div>
    </div>
  );
}

export function Alert({ type, children }: { type: "success" | "error" | "info"; children: ReactNode }) {
  const className =
    type === "success" ? "alert-success" : type === "info" ? "alert-info" : "alert-error";
  return <div className={cn("alert", className)}>{children}</div>;
}

export function LoadingState({ message = "Loading…" }: { message?: string }) {
  return (
    <div className="loading-state">
      <div className="spinner" />
      {message}
    </div>
  );
}

export function EmptyState({ message, icon }: { message: string; icon?: ReactNode }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">{icon ?? <IconEmptyFallback />}</div>
      <p>{message}</p>
    </div>
  );
}

function IconEmptyFallback() {
  return (
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}

export function Modal({
  title,
  onClose,
  children,
  footer,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="modal-overlay" onClick={onClose} role="presentation">
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="modal-header">
          <h2 className="modal-title">{title}</h2>
          <button type="button" className="btn btn-ghost btn-icon" onClick={onClose} aria-label="Close">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6 6 18" /><path d="m6 6 12 12" />
            </svg>
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}
