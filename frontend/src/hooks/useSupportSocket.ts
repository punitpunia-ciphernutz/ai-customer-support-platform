import { useEffect, useRef } from "react";

const WS_BASE = import.meta.env.VITE_WS_BASE_URL ?? "ws://localhost:8000/ws";

type Handler = (event: { name?: string; payload?: unknown }) => void;

export function useSupportSocket({
  token,
  onEvent,
}: {
  token: string | null;
  onEvent: Handler;
}) {
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  useEffect(() => {
    const url = token ? `${WS_BASE}?token=${encodeURIComponent(token)}` : WS_BASE;
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
  }, [token]);
}
