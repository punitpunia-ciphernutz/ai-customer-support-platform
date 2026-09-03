import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, API_BASE, ApiError } from "@/services/api/client";
import {
  Alert,
  EmptyState,
  LoadingState,
  Modal,
  PageHeader,
  StatCard,
  TableSearchBar,
} from "@/components/ui";
import { IconBook, IconChevronLeft, IconPlus, IconRefresh, IconTrash } from "@/components/ui/icons";
import { formatDate, statusClass } from "@/utils/format";

type KnowledgeSource = {
  id: string;
  name: string;
  type: "TEXT" | "PDF" | "URL";
  status: string;
  created_at: string;
};

type Document = {
  id: string;
  knowledge_source_id: string;
  title: string;
  status: string;
  error_message: string | null;
  created_at: string;
};

function getToken(): string | null {
  return localStorage.getItem("access_token");
}

function isRetryableStatus(status: string): boolean {
  return status === "PENDING" || status === "FAILED" || status === "PROCESSING";
}

export function KnowledgePage() {
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [type, setType] = useState<"TEXT" | "PDF" | "URL">("TEXT");
  const [search, setSearch] = useState("");

  const sources = useQuery({
    queryKey: ["knowledge-sources"],
    queryFn: () => api<KnowledgeSource[]>("/knowledge/sources"),
    refetchInterval: 4000,
  });

  const create = useMutation({
    mutationFn: () =>
      api<KnowledgeSource>("/knowledge/sources", {
        method: "POST",
        body: JSON.stringify({ name, type, configuration: {} }),
      }),
    onSuccess: () => {
      setName("");
      setShowCreate(false);
      void qc.invalidateQueries({ queryKey: ["knowledge-sources"] });
    },
  });

  const retrySource = useMutation({
    mutationFn: (sourceId: string) =>
      api(`/knowledge/sources/${sourceId}/retry`, { method: "POST" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["knowledge-sources"] });
    },
  });

  const deleteSource = useMutation({
    mutationFn: (sourceId: string) =>
      api(`/knowledge/sources/${sourceId}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["knowledge-sources"] });
    },
  });

  const completed = (sources.data ?? []).filter((s) => s.status === "COMPLETED").length;

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    let list = sources.data ?? [];
    if (q) {
      list = list.filter(
        (s) =>
          s.name.toLowerCase().includes(q) ||
          s.type.toLowerCase().includes(q) ||
          s.status.toLowerCase().includes(q)
      );
    }
    return list;
  }, [sources.data, search]);

  return (
    <div className="page-scroll">
      <PageHeader
        title="Knowledge Base"
        description="Add sources, ingest documents, and watch status update as Celery processes them."
        action={
          <button type="button" className="btn btn-primary" onClick={() => setShowCreate(true)}>
            <IconPlus size={16} />
            Add Source
          </button>
        }
      />

      <div className="stats-grid">
        <StatCard icon={<IconBook size={20} />} value={sources.data?.length ?? 0} label="Total Sources" color="green" />
        <StatCard icon={<IconBook size={20} />} value={completed} label="Completed" sublabel="Ready for retrieval" color="blue" />
      </div>

      {sources.isLoading && <LoadingState message="Loading sources…" />}
      {sources.isError && (
        <Alert type="error">
          {sources.error instanceof ApiError ? sources.error.message : "Failed to load sources."}
        </Alert>
      )}

      {!sources.isLoading && !(sources.data?.length) && (
        <EmptyState message="No knowledge sources yet. Add one to start ingesting documents." />
      )}

      {!sources.isLoading && (sources.data?.length ?? 0) > 0 && (
        <div className="table-wrap">
          <TableSearchBar
            value={search}
            placeholder="Search knowledge…"
            onChange={setSearch}
          />

          {!filtered.length ? (
            <EmptyState message="No sources match your search." />
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((s) => (
                  <tr key={s.id}>
                    <td className="cell-primary">{s.name}</td>
                    <td><span className="badge badge-normal">{s.type}</span></td>
                    <td><span className={statusClass(s.status.toLowerCase())}>{s.status}</span></td>
                    <td className="text-sm text-muted">{formatDate(s.created_at)}</td>
                    <td>
                      <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
                        {isRetryableStatus(s.status) && (
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm btn-icon"
                            disabled={retrySource.isPending}
                            onClick={() => retrySource.mutate(s.id)}
                            aria-label="Retry ingestion"
                            title="Re-queue ingestion (requires Celery worker)"
                          >
                            <IconRefresh size={14} />
                          </button>
                        )}
                        <Link to={`/knowledge/${s.id}`} className="btn btn-secondary btn-sm">
                          Manage →
                        </Link>
                        <button
                          type="button"
                          className="btn btn-danger btn-sm btn-icon"
                          onClick={() => { if (confirm(`Delete source "${s.name}" and all its documents?`)) deleteSource.mutate(s.id); }}
                          aria-label="Delete source"
                        >
                          <IconTrash size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {showCreate && (
        <Modal
          title="Add Knowledge Source"
          onClose={() => setShowCreate(false)}
          footer={
            <>
              <button type="button" className="btn btn-ghost" onClick={() => setShowCreate(false)}>Cancel</button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={create.isPending || !name.trim()}
                onClick={() => create.mutate()}
              >
                Add Source
              </button>
            </>
          }
        >
          <div className="form-field">
            <label className="form-label">Source name</label>
            <input
              className="form-input"
              placeholder="e.g. FAQ, Product Docs"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="form-field">
            <label className="form-label">Type</label>
            <select className="form-select" value={type} onChange={(e) => setType(e.target.value as typeof type)}>
              <option value="TEXT">TEXT</option>
              <option value="PDF">PDF</option>
              <option value="URL">URL</option>
            </select>
          </div>
        </Modal>
      )}
    </div>
  );
}

export function KnowledgeSourcePage() {
  const { sourceId = "" } = useParams();
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const sources = useQuery({
    queryKey: ["knowledge-sources"],
    queryFn: () => api<KnowledgeSource[]>("/knowledge/sources"),
  });
  const source = useMemo(
    () => sources.data?.find((s) => s.id === sourceId),
    [sources.data, sourceId]
  );

  const documents = useQuery({
    queryKey: ["knowledge-documents", sourceId],
    queryFn: () => api<Document[]>(`/knowledge/sources/${sourceId}/documents`),
    enabled: Boolean(sourceId),
    refetchInterval: 2500,
  });

  const addText = useMutation({
    mutationFn: () =>
      api(`/knowledge/sources/${sourceId}/documents/text`, {
        method: "POST",
        body: JSON.stringify({ title, content }),
      }),
    onSuccess: () => {
      setTitle("");
      setContent("");
      void qc.invalidateQueries({ queryKey: ["knowledge-documents", sourceId] });
      void qc.invalidateQueries({ queryKey: ["knowledge-sources"] });
    },
  });

  const addUrl = useMutation({
    mutationFn: () =>
      api(`/knowledge/sources/${sourceId}/documents/url`, {
        method: "POST",
        body: JSON.stringify({ title, url }),
      }),
    onSuccess: () => {
      setTitle("");
      setUrl("");
      void qc.invalidateQueries({ queryKey: ["knowledge-documents", sourceId] });
      void qc.invalidateQueries({ queryKey: ["knowledge-sources"] });
    },
  });

  async function addPdf(e: FormEvent) {
    e.preventDefault();
    if (!file || !title.trim()) return;
    const token = getToken();
    const form = new FormData();
    form.append("title", title);
    form.append("file", file);
    const res = await fetch(`${API_BASE}/knowledge/sources/${sourceId}/documents/pdf`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      body: form,
    });
    if (!res.ok) throw new Error(await res.text());
    setTitle("");
    setFile(null);
    void qc.invalidateQueries({ queryKey: ["knowledge-documents", sourceId] });
    void qc.invalidateQueries({ queryKey: ["knowledge-sources"] });
  }

  const remove = useMutation({
    mutationFn: (documentId: string) =>
      api(`/knowledge/documents/${documentId}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["knowledge-documents", sourceId] });
    },
  });

  const retryDocument = useMutation({
    mutationFn: (documentId: string) =>
      api(`/knowledge/documents/${documentId}/retry`, { method: "POST" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["knowledge-documents", sourceId] });
      void qc.invalidateQueries({ queryKey: ["knowledge-sources"] });
    },
  });

  return (
    <div className="page-scroll">
      <Link to="/knowledge" className="btn btn-ghost btn-sm mb-4" style={{ display: "inline-flex" }}>
        <IconChevronLeft size={16} />
        Knowledge Base
      </Link>

      <PageHeader
        title={source?.name ?? "Source"}
        description={`Type: ${source?.type ?? "…"} · Status: ${source?.status ?? "…"}`}
      />

      <div className="card mb-6">
        <h2 className="section-title">Add Document</h2>

        {source?.type === "TEXT" && (
          <form
            onSubmit={(e) => { e.preventDefault(); addText.mutate(); }}
            style={{ display: "grid", gap: "0.75rem", maxWidth: 560 }}
          >
            <input className="form-input" placeholder="Document title" value={title} onChange={(e) => setTitle(e.target.value)} />
            <textarea className="form-textarea" placeholder="Paste FAQ / help text" rows={5} value={content} onChange={(e) => setContent(e.target.value)} />
            <button type="submit" className="btn btn-primary" disabled={addText.isPending} style={{ justifySelf: "start" }}>
              Add Text Document
            </button>
          </form>
        )}

        {source?.type === "URL" && (
          <form
            onSubmit={(e) => { e.preventDefault(); addUrl.mutate(); }}
            style={{ display: "grid", gap: "0.75rem", maxWidth: 560 }}
          >
            <input className="form-input" placeholder="Document title" value={title} onChange={(e) => setTitle(e.target.value)} />
            <input className="form-input" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />
            <button type="submit" className="btn btn-primary" disabled={addUrl.isPending} style={{ justifySelf: "start" }}>
              Add URL Document
            </button>
          </form>
        )}

        {source?.type === "PDF" && (
          <form onSubmit={(e) => void addPdf(e)} style={{ display: "grid", gap: "0.75rem", maxWidth: 560 }}>
            <input className="form-input" placeholder="Document title" value={title} onChange={(e) => setTitle(e.target.value)} />
            <input type="file" accept="application/pdf" className="form-input" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <button type="submit" className="btn btn-primary" style={{ justifySelf: "start" }}>Upload PDF</button>
          </form>
        )}
      </div>

      <h2 className="section-title">Documents</h2>
      {documents.isLoading && <LoadingState message="Loading documents…" />}

      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Title</th>
              <th>Status</th>
              <th>Created</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(documents.data ?? []).map((d) => (
              <tr key={d.id}>
                <td className="cell-primary">
                  <Link to={`/knowledge/${sourceId}/documents/${d.id}`} className="link">{d.title}</Link>
                </td>
                <td><span className={statusClass(d.status.toLowerCase())}>{d.status}</span></td>
                <td className="text-sm text-muted">{formatDate(d.created_at)}</td>
                <td>
                  <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
                    {isRetryableStatus(d.status) && (
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm btn-icon"
                        disabled={retryDocument.isPending}
                        onClick={() => retryDocument.mutate(d.id)}
                        aria-label="Retry ingestion"
                        title="Re-queue ingestion (requires Celery worker)"
                      >
                        <IconRefresh size={14} />
                      </button>
                    )}
                    <button type="button" className="btn btn-danger btn-sm btn-icon" onClick={() => remove.mutate(d.id)} aria-label="Delete">
                      <IconTrash size={14} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!documents.isLoading && !documents.data?.length && (
          <EmptyState message="No documents yet." />
        )}
      </div>
    </div>
  );
}
