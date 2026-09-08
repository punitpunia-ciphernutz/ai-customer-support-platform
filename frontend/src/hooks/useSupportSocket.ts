import { useEffect, useRef } from "react";

const WS_BASE = import.meta.env.VITE_WS_BASE_URL ?? "ws://localhost:8000/ws";

type Handler = (event: { name?: string; payload?: unknown }) => void;

/** Agent inbox: authenticated `/ws?token=…`. Public chat: `/ws/public` (optional visitor token). */
export function useSupportSocket({
  token,
  onEvent,
  publicSocket = false,
  conversationId = null,
  enabled = true,
}: {
  token: string | null;
  onEvent: Handler;
  publicSocket?: boolean;
  conversationId?: string | null;
  /** When false, do not open a socket (e.g. Settings Live Preview sandbox). */
  enabled?: boolean;
}) {
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  useEffect(() => {
    if (!enabled) return;
    let url: string;
    if (publicSocket) {
      const base = WS_BASE.replace(/\/ws$/, "/ws/public");
      const publicBase = base.includes("/ws/public") ? base : `${WS_BASE}/public`;
      url = token ? `${publicBase}?token=${encodeURIComponent(token)}` : publicBase;
    } else if (!token) {
      return;
    } else {
      url = `${WS_BASE}?token=${encodeURIComponent(token)}`;
    }
    const ws = new WebSocket(url);
    ws.onopen = () => {
      if (conversationId && token && publicSocket && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "subscribe", conversation_id: conversationId }));
      }
    };
    ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data as string);
        handlerRef.current(data);
      } catch {
        /* ignore */
      }
    };
    const ping = window.setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send("ping");
    }, 25000);
    return () => {
      window.clearInterval(ping);
      ws.close();
    };
  }, [token, publicSocket, conversationId, enabled]);
}
