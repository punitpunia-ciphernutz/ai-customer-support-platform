import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "@/services/api/client";
import { useAuth } from "@/features/auth/AuthContext";
import { useSupportSocket } from "@/hooks/useSupportSocket";
import { IconBell, IconEmpty, IconX } from "@/components/ui/icons";
import { formatRelative } from "@/utils/format";
import { cn } from "@/utils/cn";
import type { AppNotification } from "@/types";

type ToastState = {
  id: string;
  title: string;
  body: string;
  event_type: string;
};

function playNotifyChime() {
  try {
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const now = ctx.currentTime;
    const gain = ctx.createGain();
    gain.connect(ctx.destination);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.08, now + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.35);

    const osc = ctx.createOscillator();
    osc.type = "sine";
    osc.frequency.setValueAtTime(880, now);
    osc.frequency.exponentialRampToValueAtTime(1320, now + 0.12);
    osc.connect(gain);
    osc.start(now);
    osc.stop(now + 0.36);
    void ctx.resume().finally(() => {
      window.setTimeout(() => void ctx.close(), 500);
    });
  } catch {
    /* ignore autoplay / unsupported */
  }
}

export function NotificationBell() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [ringing, setRinging] = useState(false);
  const [toast, setToast] = useState<ToastState | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const toastTimer = useRef<number | null>(null);
  const ringTimer = useRef<number | null>(null);
  const baseTitle = useRef(typeof document !== "undefined" ? document.title : "Support");

  const notifications = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api<AppNotification[]>("/notifications"),
    enabled: Boolean(user),
    refetchInterval: 60_000,
  });

  const announceNew = (payload: {
    notification_id?: string;
    title?: string;
    body?: string;
    event_type?: string;
  }) => {
    setRinging(true);
    if (ringTimer.current) window.clearTimeout(ringTimer.current);
    ringTimer.current = window.setTimeout(() => setRinging(false), 1800);

    playNotifyChime();

    const id = payload.notification_id ?? String(Date.now());
    setToast({
      id,
      title: payload.title || "New notification",
      body: payload.body || "Something needs your attention.",
      event_type: payload.event_type || "ALERT",
    });
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 6500);
  };

  useSupportSocket({
    token: localStorage.getItem("access_token"),
    onEvent: (event) => {
      if (event.name !== "notification.created") return;
      const payload = event.payload as {
        user_id?: string;
        notification_id?: string;
        title?: string;
        body?: string;
        event_type?: string;
      } | undefined;
      if (payload?.user_id && user && payload.user_id !== user.id) return;
      void qc.invalidateQueries({ queryKey: ["notifications"] });
      announceNew(payload ?? {});
    },
  });

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
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

  useEffect(() => {
    return () => {
      if (toastTimer.current) window.clearTimeout(toastTimer.current);
      if (ringTimer.current) window.clearTimeout(ringTimer.current);
      document.title = baseTitle.current;
    };
  }, []);

  const markRead = useMutation({
    mutationFn: (id: string) => api(`/notifications/${id}/read`, { method: "PATCH" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const markAll = useMutation({
    mutationFn: () => api<{ marked: number }>("/notifications/read-all", { method: "POST" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const items = notifications.data ?? [];
  const unread = items.filter((n) => !n.read_at).length;

  useEffect(() => {
    if (unread > 0) {
      document.title = `(${unread}) ${baseTitle.current}`;
    } else {
      document.title = baseTitle.current;
    }
  }, [unread]);

  const openItem = (n: AppNotification) => {
    if (!n.read_at) markRead.mutate(n.id);
    setOpen(false);
    setToast(null);
    const conversationId = n.metadata?.conversation_id;
    const ticketId = n.metadata?.ticket_id;
    if (typeof conversationId === "string" && conversationId) {
      navigate(`/?c=${encodeURIComponent(conversationId)}`);
    } else if (typeof ticketId === "string" && ticketId) {
      navigate(`/tickets?t=${encodeURIComponent(ticketId)}`);
    }
  };

  const openFromToast = () => {
    setToast(null);
    setOpen(true);
  };

  return (
    <>
      <div className="notification-bell" ref={panelRef}>
        <button
          type="button"
          className={cn(
            "sidebar-link notification-bell-btn",
            unread > 0 && "has-unread",
            ringing && "is-ringing",
          )}
          aria-label={unread > 0 ? `Notifications, ${unread} unread` : "Notifications"}
          aria-expanded={open}
          onClick={() => {
            setOpen((v) => !v);
            setRinging(false);
            setToast(null);
          }}
        >
          <span className="notification-bell-icon-wrap" aria-hidden>
            <IconBell size={18} />
            {unread > 0 && <span className="notification-dot" />}
          </span>
          Notifications
          {unread > 0 && (
            <span className={cn("notification-badge", ringing && "pulse")}>
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </button>

        {open && (
          <div className="notification-panel" role="dialog" aria-label="Notifications">
            <div className="notification-panel-header">
              <div>
                <strong>Notifications</strong>
                <div className="notification-panel-sub">
                  {unread > 0 ? `${unread} unread` : "You're all caught up"}
                </div>
              </div>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={unread === 0 || markAll.isPending}
                onClick={() => markAll.mutate()}
              >
                Mark all read
              </button>
            </div>
            <div className="notification-panel-list">
              {notifications.isLoading && (
                <p className="notification-empty text-sm text-muted">Loading…</p>
              )}
              {!notifications.isLoading && items.length === 0 && (
                <div className="notification-empty">
                  <IconEmpty size={36} />
                  <p>No notifications yet</p>
                  <span className="text-sm text-muted">Alerts from automations and escalations will show up here.</span>
                </div>
              )}
              {items.map((n) => (
                <button
                  key={n.id}
                  type="button"
                  className={cn("notification-item", !n.read_at && "unread")}
                  onClick={() => openItem(n)}
                >
                  <span className={cn("notification-item-rail", !n.read_at && "active")} aria-hidden />
                  <div className="notification-item-content">
                    <div className="notification-item-title-row">
                      <div className="notification-item-title">{n.title}</div>
                      {!n.read_at && <span className="notification-item-new">New</span>}
                    </div>
                    <div className="notification-item-body">{n.body}</div>
                    <div className="notification-item-meta">
                      <span>{n.event_type.replace(/_/g, " ").toLowerCase()}</span>
                      <span>{formatRelative(n.created_at)}</span>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {toast && (
        <div className="notification-toast" role="status" aria-live="polite">
          <button type="button" className="notification-toast-main" onClick={openFromToast}>
            <span className="notification-toast-icon" aria-hidden>
              <IconBell size={16} />
            </span>
            <span className="notification-toast-copy">
              <span className="notification-toast-label">New alert</span>
              <strong className="notification-toast-title">{toast.title}</strong>
              <span className="notification-toast-body">{toast.body}</span>
            </span>
          </button>
          <button
            type="button"
            className="notification-toast-dismiss"
            aria-label="Dismiss"
            onClick={() => setToast(null)}
          >
            <IconX size={14} />
          </button>
        </div>
      )}
    </>
  );
}
