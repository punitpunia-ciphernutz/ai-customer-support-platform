import { useState } from "react";
import type { ChatWidget, WidgetUpdateInput } from "@/features/widgets/types";

const POSITIONS = [
  { value: "bottom-right", label: "Bottom right" },
  { value: "bottom-left", label: "Bottom left" },
] as const;

function ColorField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <label className="form-field">
      <span>{label}</span>
      <div className="widget-color-field">
        <input
          type="color"
          className="widget-color-swatch"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-label={label}
        />
        <input
          className="form-input"
          value={value}
          onChange={(e) => {
            const next = e.target.value.trim();
            if (/^#[0-9a-fA-F]{6}$/.test(next) || /^#[0-9a-fA-F]{3}$/.test(next)) {
              onChange(next.length === 4
                ? `#${next[1]}${next[1]}${next[2]}${next[2]}${next[3]}${next[3]}`
                : next);
            } else {
              onChange(e.target.value);
            }
          }}
          placeholder="#3B66F5"
          spellCheck={false}
        />
      </div>
    </label>
  );
}

export function WidgetForm({
  widget,
  saving,
  error,
  onSave,
}: {
  widget: ChatWidget;
  saving?: boolean;
  error?: string | null;
  onSave: (patch: WidgetUpdateInput) => void;
}) {
  const [name, setName] = useState(widget.name);
  const [status, setStatus] = useState(widget.status);
  const [domains, setDomains] = useState((widget.allowed_domains ?? []).join("\n"));
  const [welcome, setWelcome] = useState(widget.welcome_message);
  const [offline, setOffline] = useState(widget.offline_message ?? "");
  const [requireName, setRequireName] = useState(widget.require_name);
  const [requireEmail, setRequireEmail] = useState(widget.require_email);
  const [primary, setPrimary] = useState(widget.appearance?.primary_color ?? "#3B66F5");
  const [textColor, setTextColor] = useState(widget.appearance?.text_color ?? "#FFFFFF");
  const [position, setPosition] = useState(widget.appearance?.launcher_position ?? "bottom-right");
  const [launcherText, setLauncherText] = useState(widget.appearance?.launcher_text ?? "Chat");

  return (
    <form
      className="form-stack"
      onSubmit={(e) => {
        e.preventDefault();
        const normalizedPrimary = /^#[0-9a-fA-F]{6}$/.test(primary) ? primary : "#3B66F5";
        const normalizedText = /^#[0-9a-fA-F]{6}$/.test(textColor) ? textColor : "#FFFFFF";
        onSave({
          name: name.trim(),
          status,
          allowed_domains: domains
            .split(/[\n,]/)
            .map((d) => d.trim())
            .filter(Boolean),
          welcome_message: welcome,
          offline_message: offline || null,
          require_name: requireName,
          require_email: requireEmail,
          appearance: {
            ...(widget.appearance ?? {}),
            primary_color: normalizedPrimary,
            text_color: normalizedText,
            launcher_position: position,
            launcher_text: launcherText.trim() || "Chat",
          },
        });
      }}
    >
      {error && <div className="alert alert-error">{error}</div>}

      <label className="form-field">
        <span>Name</span>
        <input className="form-input" value={name} onChange={(e) => setName(e.target.value)} required />
      </label>

      <label className="form-field">
        <span>Status</span>
        <select
          className="form-select"
          value={status}
          onChange={(e) => setStatus(e.target.value as ChatWidget["status"])}
        >
          <option value="DRAFT">Draft</option>
          <option value="ACTIVE">Active</option>
          <option value="INACTIVE">Inactive</option>
        </select>
      </label>

      <label className="form-field">
        <span>Allowed domains (one per line)</span>
        <textarea
          className="form-input"
          rows={4}
          value={domains}
          onChange={(e) => setDomains(e.target.value)}
          placeholder={"example.com\nwww.example.com\n*.staging.example.com"}
        />
        <span className="form-hint">
          Active widgets require at least one domain. Use exact hosts or a single-level wildcard like
          *.example.com.
        </span>
      </label>

      <label className="form-field">
        <span>Welcome message</span>
        <textarea className="form-input" rows={3} value={welcome} onChange={(e) => setWelcome(e.target.value)} />
      </label>

      <label className="form-field">
        <span>Offline message</span>
        <textarea className="form-input" rows={2} value={offline} onChange={(e) => setOffline(e.target.value)} />
      </label>

      <div className="form-row" style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap" }}>
        <label className="form-check">
          <input type="checkbox" checked={requireName} onChange={(e) => setRequireName(e.target.checked)} />
          Require name
        </label>
        <label className="form-check">
          <input type="checkbox" checked={requireEmail} onChange={(e) => setRequireEmail(e.target.checked)} />
          Require email
        </label>
      </div>

      <div className="widget-appearance-block">
        <h4 className="widget-appearance-title">Appearance</h4>
        <div className="widget-appearance-grid">
          <ColorField label="Primary color" value={primary} onChange={setPrimary} />
          <ColorField label="Text color" value={textColor} onChange={setTextColor} />
          <label className="form-field">
            <span>Launcher position</span>
            <select className="form-select" value={position} onChange={(e) => setPosition(e.target.value)}>
              {POSITIONS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <label className="form-field">
            <span>Launcher text</span>
            <input
              className="form-input"
              value={launcherText}
              onChange={(e) => setLauncherText(e.target.value)}
              placeholder="Chat"
            />
          </label>
        </div>
        <div className="widget-appearance-preview" aria-hidden>
          <div
            className="widget-appearance-preview-chip"
            style={{ background: /^#[0-9a-fA-F]{6}$/.test(primary) ? primary : "#3B66F5", color: /^#[0-9a-fA-F]{6}$/.test(textColor) ? textColor : "#fff" }}
          >
            {launcherText.trim() || "Chat"}
          </div>
          <span className="form-hint">
            Position: {position === "bottom-left" ? "bottom left" : "bottom right"}
          </span>
        </div>
      </div>

      <p className="form-hint">
        AI mode is configured under Settings → Channels → Web Chat. Widgets inherit that channel
        configuration.
      </p>

      <button type="submit" className="btn btn-primary" disabled={saving}>
        {saving ? "Saving…" : "Save changes"}
      </button>
    </form>
  );
}
