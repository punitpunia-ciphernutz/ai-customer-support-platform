import { useEffect, useRef } from "react";
import {
  WIDGET_PREVIEW_UPDATE,
  type WidgetPreviewDraft,
} from "@/widget/previewMock";

function ensurePreviewParam(url: string): string {
  try {
    const parsed = new URL(url, window.location.origin);
    if (parsed.searchParams.get("preview") !== "true") {
      parsed.searchParams.set("preview", "true");
    }
    return parsed.toString();
  } catch {
    return url.includes("preview=true") ? url : `${url}${url.includes("?") ? "&" : "?"}preview=true`;
  }
}

export function WidgetPreview({
  frameUrl,
  draft,
}: {
  frameUrl: string | null;
  draft?: WidgetPreviewDraft | null;
}) {
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const src = frameUrl ? ensurePreviewParam(frameUrl) : null;

  const postDraft = () => {
    if (!draft || !iframeRef.current?.contentWindow) return;
    iframeRef.current.contentWindow.postMessage(
      {
        type: WIDGET_PREVIEW_UPDATE,
        name: draft.name,
        welcome_message: draft.welcome_message,
        appearance: draft.appearance,
      },
      "*"
    );
  };

  useEffect(() => {
    postDraft();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-post whenever draft or frame URL changes
  }, [draft, src]);

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      const data = event.data || {};
      if (data.type === "WIDGET_READY") {
        postDraft();
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, src]);

  const primary =
    draft?.appearance?.primary_color && /^#[0-9a-fA-F]{6}$/.test(draft.appearance.primary_color)
      ? draft.appearance.primary_color
      : "#3B66F5";
  const textColor =
    draft?.appearance?.text_color && /^#[0-9a-fA-F]{6}$/.test(draft.appearance.text_color)
      ? draft.appearance.text_color
      : "#FFFFFF";
  const launcherText = draft?.appearance?.launcher_text?.trim() || "Chat";
  const launcherPosition = draft?.appearance?.launcher_position === "bottom-left" ? "left" : "right";

  if (!src) {
    return (
      <div className="panel" style={{ padding: "1rem", minHeight: 420 }}>
        <h3 style={{ marginTop: 0 }}>Live preview</h3>
        <p className="text-muted">Generate a preview token to load the widget iframe.</p>
      </div>
    );
  }

  return (
    <div className="panel" style={{ padding: "1rem" }}>
      <h3 style={{ marginTop: 0 }}>Live preview</h3>
      <p className="text-muted" style={{ marginTop: 0 }}>
        Sandbox appearance preview with sample messages — not real conversation history.
      </p>
      <div
        style={{
          position: "relative",
          height: 480,
          borderRadius: 12,
          overflow: "hidden",
          border: "1px solid var(--border, #e5e7eb)",
          background: "#f7f8fa",
        }}
      >
        <iframe
          ref={iframeRef}
          title="Widget preview"
          src={src}
          style={{ width: "100%", height: "100%", border: 0 }}
        />
      </div>
      <div
        aria-hidden
        style={{
          display: "flex",
          justifyContent: launcherPosition === "left" ? "flex-start" : "flex-end",
          marginTop: "0.75rem",
        }}
      >
        <div
          style={{
            background: primary,
            color: textColor,
            borderRadius: 999,
            padding: "0.65rem 1.1rem",
            fontSize: "0.875rem",
            fontWeight: 600,
            boxShadow: "0 4px 14px rgba(15, 23, 42, 0.12)",
          }}
        >
          {launcherText}
        </div>
      </div>
    </div>
  );
}
