import type { StoredVisitorState } from "@/widget/types";
import { storageKey } from "@/widget/types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export class WidgetApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** True when the backend rejected the visitor JWT (expired, secret rotated, mismatch). */
export function isVisitorAuthError(error: unknown): boolean {
  return (
    error instanceof WidgetApiError &&
    error.status === 401 &&
    /visitor token/i.test(error.message)
  );
}

export async function widgetApi<T>(
  path: string,
  options: RequestInit & {
    pageHost?: string;
    visitorToken?: string | null;
    previewToken?: string | null;
    /** When set, clears persisted visitor state on visitor-token 401s. */
    publicId?: string;
  } = {}
): Promise<T> {
  const { pageHost, visitorToken, previewToken, publicId, headers, ...rest } = options;
  const h = new Headers(headers);
  h.set("Content-Type", "application/json");
  if (pageHost) h.set("X-Widget-Page-Host", pageHost);
  if (visitorToken) h.set("Authorization", `Bearer ${visitorToken}`);
  if (previewToken) h.set("X-Widget-Preview-Token", previewToken);

  const res = await fetch(`${API_BASE}${path}`, { ...rest, headers: h });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* ignore */
    }
    const message = typeof detail === "string" ? detail : JSON.stringify(detail);
    const err = new WidgetApiError(res.status, message);
    if (publicId && isVisitorAuthError(err)) {
      clearVisitorState(publicId);
    }
    throw err;
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export function loadVisitorState(publicId: string): StoredVisitorState | null {
  try {
    const raw = localStorage.getItem(storageKey(publicId));
    if (!raw) return null;
    return JSON.parse(raw) as StoredVisitorState;
  } catch {
    return null;
  }
}

export function saveVisitorState(publicId: string, state: StoredVisitorState) {
  localStorage.setItem(storageKey(publicId), JSON.stringify(state));
}

/**
 * Drop the persisted visitor JWT (and conversation pointer).
 * Keeps `visitor_key` when present so a re-issued session can resume the same anonymous visitor.
 */
export function clearVisitorState(publicId: string) {
  try {
    const raw = localStorage.getItem(storageKey(publicId));
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw) as StoredVisitorState;
      if (parsed.visitor_key) {
        localStorage.setItem(
          storageKey(publicId),
          JSON.stringify({
            visitor_key: parsed.visitor_key,
            visitor_token: "",
            customer_id: "",
            conversation_id: null,
          } satisfies StoredVisitorState)
        );
        return;
      }
    } catch {
      /* fall through to full remove */
    }
    localStorage.removeItem(storageKey(publicId));
  } catch {
    /* ignore quota / private-mode failures */
  }
}
