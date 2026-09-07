import { useState } from "react";
import type { EmbedSnippet } from "@/features/widgets/types";

export function EmbedSnippetCard({ snippet }: { snippet: EmbedSnippet }) {
  const [copied, setCopied] = useState(false);

  return (
    <div className="panel" style={{ padding: "1rem" }}>
      <h3 style={{ marginTop: 0 }}>Embed snippet</h3>
      <p className="text-muted" style={{ marginTop: 0 }}>
        Paste this before <code>&lt;/body&gt;</code> on an allowlisted site.
      </p>
      <pre
        style={{
          background: "var(--surface-2, #111827)",
          color: "#e5e7eb",
          padding: "0.85rem",
          borderRadius: 8,
          overflow: "auto",
          fontSize: "0.8rem",
        }}
      >
        {snippet.snippet}
      </pre>
      <button
        type="button"
        className="btn btn-secondary"
        onClick={async () => {
          await navigator.clipboard.writeText(snippet.snippet);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        }}
      >
        {copied ? "Copied" : "Copy snippet"}
      </button>
      <ol style={{ marginTop: "1rem", paddingLeft: "1.2rem" }} className="text-muted">
        <li>Copy the snippet above.</li>
        <li>Paste it on your website before the closing body tag.</li>
        <li>Add your site hostname to Allowed domains and set status to Active.</li>
        <li>Open the site and confirm the chat bubble appears.</li>
      </ol>
    </div>
  );
}
