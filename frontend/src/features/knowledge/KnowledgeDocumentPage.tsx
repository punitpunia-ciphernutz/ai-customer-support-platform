import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "@/services/api/client";
import { Alert, LoadingState, PageHeader } from "@/components/ui";
import { IconChevronLeft, IconRefresh, IconTrash } from "@/components/ui/icons";
import { statusClass } from "@/utils/format";

type KnowledgeSource = {
  id: string;
  name: string;
  type: "TEXT" | "PDF" | "URL";
  status: string;
  created_at: string;
};

type DocumentDetail = {
  id: string;
  knowledge_source_id: string;
  title: string;
  content: string | null;
  source_url: string | null;
  status: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export function KnowledgeDocumentPage() {
  const { sourceId = "", documentId = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");

  const sources = useQuery({
    queryKey: ["knowledge-sources"],
    queryFn: () => api<KnowledgeSource[]>("/knowledge/sources"),
  });
  const source = sources.data?.find((s) => s.id === sourceId);

  const document = useQuery({
    queryKey: ["knowledge-document", documentId],
    queryFn: () => api<DocumentDetail>(`/knowledge/documents/${documentId}`),
    enabled: Boolean(documentId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "PENDING" || status === "PROCESSING" ? 2000 : false;
    },
  });

  const doc = document.data;
  const isText = source?.type === "TEXT";

  useEffect(() => {
    if (doc && !editing) {
      setEditTitle(doc.title);
      setEditContent(doc.content ?? "");
    }
  }, [doc, editing]);

  const update = useMutation({
    mutationFn: (body: { title?: string; content?: string }) =>
      api(`/knowledge/documents/${documentId}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      setEditing(false);
      void qc.invalidateQueries({ queryKey: ["knowledge-document", documentId] });
      void qc.invalidateQueries({ queryKey: ["knowledge-documents", sourceId] });
      void qc.invalidateQueries({ queryKey: ["knowledge-sources"] });
    },
  });

  const remove = useMutation({
    mutationFn: () => api(`/knowledge/documents/${documentId}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["knowledge-documents", sourceId] });
      navigate(`/knowledge/${sourceId}`);
    },
  });

  const retry = useMutation({
    mutationFn: () => api(`/knowledge/documents/${documentId}/retry`, { method: "POST" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["knowledge-document", documentId] });
    },
  });

  function handleSave() {
    const body: { title?: string; content?: string } = {};
    if (editTitle !== doc?.title) body.title = editTitle;
    if (editContent !== (doc?.content ?? "")) body.content = editContent;
    if (Object.keys(body).length === 0) {
      setEditing(false);
      return;
    }
    update.mutate(body);
  }

  const isProcessing = doc?.status === "PENDING" || doc?.status === "PROCESSING";

  return (
    <div className="page-scroll">
      <Link to={`/knowledge/${sourceId}`} className="btn btn-ghost btn-sm mb-4" style={{ display: "inline-flex" }}>
        <IconChevronLeft size={16} />
        {source?.name ?? "Source"}
      </Link>

      {document.isLoading && <LoadingState message="Loading document…" />}
      {document.isError && (
        <Alert type="error">
          {document.error instanceof ApiError ? document.error.message : "Failed to load document."}
        </Alert>
      )}

      {doc && (
        <>
          <PageHeader
            title={editing ? "Edit Document" : doc.title}
            description={`Status: ${doc.status}${doc.error_message ? ` — ${doc.error_message}` : ""}`}
            action={
              <div style={{ display: "flex", gap: "0.5rem" }}>
                {isProcessing && (
                  <span className={statusClass(doc.status.toLowerCase())} style={{ alignSelf: "center" }}>
                    {doc.status}…
                  </span>
                )}
                {!editing && isText && !isProcessing && (
                  <button type="button" className="btn btn-primary" onClick={() => setEditing(true)}>
                    Edit
                  </button>
                )}
                {(doc.status === "FAILED" || doc.status === "PENDING") && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-icon"
                    onClick={() => retry.mutate()}
                    disabled={retry.isPending}
                    aria-label="Retry ingestion"
                  >
                    <IconRefresh size={16} />
                  </button>
                )}
                <button
                  type="button"
                  className="btn btn-danger btn-icon"
                  onClick={() => { if (confirm("Delete this document?")) remove.mutate(); }}
                  aria-label="Delete"
                >
                  <IconTrash size={16} />
                </button>
              </div>
            }
          />

          {editing ? (
            <div className="card" style={{ display: "grid", gap: "0.75rem", maxWidth: 720 }}>
              <div className="form-field">
                <label className="form-label">Title</label>
                <input
                  className="form-input"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                />
              </div>
              <div className="form-field">
                <label className="form-label">Content</label>
                <textarea
                  className="form-textarea"
                  rows={20}
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  style={{ fontFamily: "monospace", fontSize: "0.85rem" }}
                />
              </div>
              {update.isError && (
                <Alert type="error">
                  {update.error instanceof ApiError ? update.error.message : "Failed to save."}
                </Alert>
              )}
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={update.isPending}
                  onClick={handleSave}
                >
                  {update.isPending ? "Saving…" : "Save & Re-ingest"}
                </button>
                <button type="button" className="btn btn-ghost" onClick={() => setEditing(false)}>
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="card">
              {!isText && (
                <p className="text-sm text-muted mb-4">
                  This is a {source?.type} document. Content is read-only. Re-add the document to change its content.
                </p>
              )}
              {doc.source_url && (
                <p className="text-sm text-muted mb-4">
                  Source URL:{" "}
                  <a href={doc.source_url} target="_blank" rel="noopener noreferrer" className="link">
                    {doc.source_url}
                  </a>
                </p>
              )}
              <pre style={{
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                fontFamily: "monospace",
                fontSize: "0.85rem",
                lineHeight: 1.6,
                maxHeight: "70vh",
                overflow: "auto",
                padding: "1rem",
                background: "var(--surface-alt, rgba(255,255,255,0.03))",
                borderRadius: "0.5rem",
              }}>
                {doc.content ?? "(No content — document may still be processing)"}
              </pre>
            </div>
          )}
        </>
      )}
    </div>
  );
}
