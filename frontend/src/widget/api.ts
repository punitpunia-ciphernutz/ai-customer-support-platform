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

export async function widgetApi<T>(
  path: string,
  options: RequestInit & {
    pageHost?: string;
    visitorToken?: string | null;
    previewToken?: string | null;
  } = {}
): Promise<T> {
  const { pageHost, visitorToken, previewToken, headers, ...rest } = options;
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
    throw new WidgetApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
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
