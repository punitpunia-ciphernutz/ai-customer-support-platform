import type { ReactNode } from "react";
import type { AIHandoffPackage } from "@/types";
import { formatPercent, statusClass } from "@/utils/format";

function hasText(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function hasNumber(value: unknown): value is number {
  return typeof value === "number" && !Number.isNaN(value);
}

function formatLabel(value: string): string {
  return value.replace(/_/g, " ");
}

function sentimentBadgeClass(sentiment: string): string {
  const s = sentiment.toUpperCase();
  if (s === "POSITIVE") return "badge badge-resolved";
  if (s === "ANGRY") return "badge badge-urgent";
  if (s === "NEGATIVE" || s === "FRUSTRATED") return "badge badge-high";
  return "badge badge-normal";
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="ai-summary-field">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Section({ title, fields }: { title: string; fields: ReactNode[] }) {
  if (fields.length === 0) return null;
  return (
    <section className="ai-summary-section">
      <h3 className="section-title">{title}</h3>
      <dl className="ai-summary-fields">{fields}</dl>
    </section>
  );
}

export function AiSummaryDrawer({
  package: pkg,
  onClose,
}: {
  package: AIHandoffPackage;
  onClose: () => void;
}) {
  const issueSummary = pkg.issue_summary || pkg.escalation_summary;
  const escalationReason = pkg.why_escalated || pkg.escalation_reason;
  const confidence = pkg.ai_confidence ?? pkg.support_confidence;
  const decision = pkg.decision || pkg.confidence_breakdown?.decision;
  const groundingScore =
    pkg.grounding_score ?? pkg.confidence_breakdown?.components?.grounding ?? null;
  const knowledgeFromSearch = (pkg.knowledge_searched ?? []).filter(hasText);
  const knowledgeFromCitations = (pkg.citations ?? []).map((c) => c.title).filter(hasText);
  const knowledge = knowledgeFromSearch.length > 0 ? knowledgeFromSearch : knowledgeFromCitations;
  const breakdown = pkg.confidence_breakdown;
  const componentEntries = breakdown?.components
    ? (Object.entries(breakdown.components) as [string, number | undefined][]).filter(([, v]) =>
        hasNumber(v)
      )
    : [];
  const reasons = (breakdown?.reasons ?? []).filter(hasText);

  const contextFields: ReactNode[] = [];
  if (hasText(issueSummary)) {
    contextFields.push(<Field key="issue" label="Issue summary">{issueSummary}</Field>);
  }
  if (hasText(pkg.intent)) {
    contextFields.push(
      <Field key="intent" label="Intent">
        <span className={statusClass(pkg.intent.toLowerCase())}>{formatLabel(pkg.intent)}</span>
      </Field>
    );
  }
  if (hasText(pkg.sentiment)) {
    contextFields.push(
      <Field key="sentiment" label="Sentiment">
        <span className={sentimentBadgeClass(pkg.sentiment)}>{formatLabel(pkg.sentiment)}</span>
      </Field>
    );
  }
  if (hasText(pkg.language)) {
    contextFields.push(<Field key="language" label="Language">{pkg.language}</Field>);
  }

  const escalationFields: ReactNode[] = [];
  if (hasText(escalationReason)) {
    escalationFields.push(
      <Field key="reason" label="Escalation reason">{escalationReason}</Field>
    );
  }
  if (hasNumber(confidence)) {
    escalationFields.push(
      <Field key="confidence" label="Support confidence">
        {formatPercent(confidence)}
      </Field>
    );
  }
  if (decision != null && hasText(String(decision))) {
    escalationFields.push(
      <Field key="decision" label="Decision">
        <span className={statusClass(String(decision).toLowerCase())}>
          {formatLabel(String(decision))}
        </span>
      </Field>
    );
  }
  if (hasText(pkg.recommended_action)) {
    escalationFields.push(
      <Field key="action" label="Recommended action">{pkg.recommended_action}</Field>
    );
  }

  const knowledgeFields: ReactNode[] = [];
  if (hasText(pkg.what_ai_tried)) {
    knowledgeFields.push(
      <Field key="tried" label="What AI tried">{pkg.what_ai_tried}</Field>
    );
  }
  if (knowledge.length > 0) {
    knowledgeFields.push(
      <Field key="knowledge" label="Knowledge searched">
        <ul className="ai-summary-list">
          {knowledge.map((title) => (
            <li key={title}>{title}</li>
          ))}
        </ul>
      </Field>
    );
  }
  if (hasNumber(groundingScore)) {
    knowledgeFields.push(
      <Field key="grounding" label="Grounding score">
        {formatPercent(groundingScore)}
      </Field>
    );
  }
  if (hasNumber(breakdown?.final) || componentEntries.length > 0 || reasons.length > 0) {
    knowledgeFields.push(
      <Field key="breakdown" label="Confidence breakdown">
        <div className="ai-summary-breakdown">
          {hasNumber(breakdown?.final) && (
            <p className="ai-summary-breakdown-final">Final: {formatPercent(breakdown.final)}</p>
          )}
          {componentEntries.length > 0 && (
            <ul className="ai-summary-list">
              {componentEntries.map(([key, value]) => (
                <li key={key}>
                  {formatLabel(key)}: {formatPercent(value)}
                </li>
              ))}
            </ul>
          )}
          {reasons.length > 0 && (
            <ul className="ai-summary-list ai-summary-reasons">
              {reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          )}
        </div>
      </Field>
    );
  }

  return (
    <div className="drawer-overlay" onClick={onClose} role="presentation">
      <aside
        className="drawer-panel"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="AI Summary"
      >
        <div className="drawer-header">
          <h2 className="modal-title">AI Summary</h2>
          <button type="button" className="btn btn-ghost btn-icon" onClick={onClose} aria-label="Close">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </button>
        </div>
        <div className="drawer-body">
          <Section title="Context" fields={contextFields} />
          <Section title="Escalation" fields={escalationFields} />
          <Section title="Knowledge / Audit" fields={knowledgeFields} />
        </div>
      </aside>
    </div>
  );
}

/** Find handoff package for a ticket from conversation messages. */
export function findTicketHandoff(
  messages: {
    metadata?: {
      ticket_id?: string;
      ai_escalation?: boolean;
      handoff_package?: AIHandoffPackage;
      ai_run_id?: string;
      citations?: { document_id?: string; title: string; chunk_id?: string }[];
    };
  }[],
  ticketId: string
): AIHandoffPackage | null {
  const note = messages.find(
    (m) => m.metadata?.ticket_id === ticketId && m.metadata?.handoff_package
  );
  const pkg = note?.metadata?.handoff_package;
  if (!pkg) return null;
  return enrichHandoff(pkg, messages, note?.metadata?.ai_run_id);
}

function enrichHandoff(
  pkg: AIHandoffPackage,
  messages: {
    metadata?: {
      ai_run_id?: string;
      citations?: { document_id?: string; title: string; chunk_id?: string }[];
    };
  }[],
  aiRunId?: string
): AIHandoffPackage {
  if ((pkg.citations?.length ?? 0) > 0 || (pkg.knowledge_searched?.length ?? 0) > 0) {
    return pkg;
  }
  const related = aiRunId
    ? messages.find((m) => m.metadata?.ai_run_id === aiRunId && m.metadata?.citations?.length)
    : messages.find((m) => m.metadata?.citations?.length);
  if (!related?.metadata?.citations?.length) return pkg;
  return { ...pkg, citations: related.metadata.citations };
}

export function handoffHasContent(pkg: AIHandoffPackage | null | undefined): boolean {
  if (!pkg) return false;
  return Boolean(
    hasText(pkg.issue_summary) ||
      hasText(pkg.escalation_summary) ||
      hasText(pkg.intent) ||
      hasText(pkg.sentiment ?? undefined) ||
      hasText(pkg.language ?? undefined) ||
      hasText(pkg.why_escalated) ||
      hasText(pkg.escalation_reason) ||
      hasNumber(pkg.ai_confidence) ||
      hasNumber(pkg.support_confidence) ||
      pkg.decision ||
      pkg.confidence_breakdown?.decision ||
      hasText(pkg.recommended_action) ||
      hasText(pkg.what_ai_tried) ||
      (pkg.knowledge_searched?.length ?? 0) > 0 ||
      (pkg.citations?.length ?? 0) > 0 ||
      hasNumber(pkg.grounding_score) ||
      pkg.confidence_breakdown
  );
}
