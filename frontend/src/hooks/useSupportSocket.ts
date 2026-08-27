import { useEffect, useRef } from "react";

const WS_BASE = import.meta.env.VITE_WS_BASE_URL ?? "ws://localhost:8000/ws";

type Handler = (event: { name?: string; payload?: unknown }) => void;

/** Agent inbox: authenticated `/ws?token=…`. Public chat: `/ws/public`. */
export function useSupportSocket({
  token,
  onEvent,
  publicSocket = false,
}: {
  token: string | null;
  onEvent: Handler;
  publicSocket?: boolean;
}) {
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  useEffect(() => {
    let url: string;
    if (publicSocket || !token) {
      const base = WS_BASE.replace(/\/ws$/, "/ws/public");
      url = base.includes("/ws/public") ? base : `${WS_BASE}/public`;
    } else {
      url = `${WS_BASE}?token=${encodeURIComponent(token)}`;
    }
    const ws = new WebSocket(url);
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
  }, [token, publicSocket]);
}
