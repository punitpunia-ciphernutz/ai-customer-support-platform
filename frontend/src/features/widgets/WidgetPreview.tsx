export function WidgetPreview({ frameUrl }: { frameUrl: string | null }) {
  if (!frameUrl) {
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
        Preview uses a short-lived token and treats localhost as allowed.
      </p>
      <div
        style={{
          height: 480,
          borderRadius: 12,
          overflow: "hidden",
          border: "1px solid var(--border, #e5e7eb)",
          background: "#f7f8fa",
        }}
      >
        <iframe title="Widget preview" src={frameUrl} style={{ width: "100%", height: "100%", border: 0 }} />
      </div>
    </div>
  );
}
