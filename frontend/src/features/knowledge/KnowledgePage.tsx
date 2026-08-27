import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, API_BASE } from "@/services/api/client";

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

export function KnowledgePage() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [type, setType] = useState<"TEXT" | "PDF" | "URL">("TEXT");

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
      void qc.invalidateQueries({ queryKey: ["knowledge-sources"] });
    },
  });

  return (
    <div className="page">
      <h1>Knowledge Base</h1>
      <p className="lede">Add sources, ingest documents, and watch status update as Celery processes them.</p>

      <form
        className="create"
        onSubmit={(e) => {
          e.preventDefault();
          if (!name.trim()) return;
          create.mutate();
        }}
      >
        <input
          placeholder="Source name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <select value={type} onChange={(e) => setType(e.target.value as typeof type)}>
          <option value="TEXT">TEXT</option>
          <option value="PDF">PDF</option>
          <option value="URL">URL</option>
        </select>
        <button type="submit" disabled={create.isPending}>
          + Add Knowledge
        </button>
      </form>

      <h2>Sources</h2>
      <ul className="list">
        {sources.data?.map((s) => (
          <li key={s.id}>
            <Link to={`/knowledge/${s.id}`}>
              <strong>{s.name}</strong>
              <span>{s.type}</span>
              <em className={`status ${s.status.toLowerCase()}`}>{s.status}</em>
            </Link>
          </li>
        ))}
        {!sources.data?.length && <li className="empty">No sources yet.</li>}
      </ul>

      <style>{pageStyles}</style>
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

  useEffect(() => {
    // keep polling while any document is pending/processing
  }, [documents.data]);

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

  return (
    <div className="page">
      <p>
        <Link to="/knowledge">← Knowledge Base</Link>
      </p>
      <h1>{source?.name ?? "Source"}</h1>
      <p className="lede">
        Type: {source?.type ?? "…"} · Status:{" "}
        <em className={`status ${(source?.status ?? "").toLowerCase()}`}>{source?.status}</em>
      </p>

      {source?.type === "TEXT" && (
        <form
          className="create stacked"
          onSubmit={(e) => {
            e.preventDefault();
            addText.mutate();
          }}
        >
          <input placeholder="Document title" value={title} onChange={(e) => setTitle(e.target.value)} />
          <textarea
            placeholder="Paste FAQ / help text"
            rows={5}
            value={content}
            onChange={(e) => setContent(e.target.value)}
          />
          <button type="submit" disabled={addText.isPending}>
            Add text document
          </button>
        </form>
      )}

      {source?.type === "URL" && (
        <form
          className="create stacked"
          onSubmit={(e) => {
            e.preventDefault();
            addUrl.mutate();
          }}
        >
          <input placeholder="Document title" value={title} onChange={(e) => setTitle(e.target.value)} />
          <input placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />
          <button type="submit" disabled={addUrl.isPending}>
            Add URL document
          </button>
        </form>
      )}

      {source?.type === "PDF" && (
        <form className="create stacked" onSubmit={(e) => void addPdf(e)}>
          <input placeholder="Document title" value={title} onChange={(e) => setTitle(e.target.value)} />
          <input type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <button type="submit">Upload PDF</button>
        </form>
      )}

      <h2>Documents</h2>
      <ul className="list">
        {documents.data?.map((d) => (
          <li key={d.id}>
            <div className="row">
              <strong>{d.title}</strong>
              <em className={`status ${d.status.toLowerCase()}`}>{d.status}</em>
              <button type="button" className="danger" onClick={() => remove.mutate(d.id)}>
                Delete
              </button>
            </div>
            {d.error_message && <small className="err">{d.error_message}</small>}
          </li>
        ))}
        {!documents.data?.length && <li className="empty">No documents yet.</li>}
      </ul>
      <style>{pageStyles}</style>
    </div>
  );
}

const pageStyles = `
  .page { padding: 1.5rem; overflow: auto; height: 100%; }
  h1 { margin-top: 0; font-family: var(--font-display); font-weight: 400; }
  .lede { color: var(--text-muted); margin-top: -0.5rem; }
  .create {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 0.5rem; margin-bottom: 1.5rem;
  }
  .create.stacked { grid-template-columns: 1fr; }
  input, select, textarea, button {
    background: var(--bg-elevated); border: 1px solid var(--border); color: var(--text);
    border-radius: 8px; padding: 0.55rem 0.7rem; font: inherit;
  }
  button { cursor: pointer; background: var(--accent); color: #111; border: none; font-weight: 600; }
  button.danger { background: transparent; color: var(--text-muted); border: 1px solid var(--border); }
  .list { list-style: none; padding: 0; margin: 0; display: grid; gap: 0.5rem; }
  .list li { background: var(--bg-elevated); border: 1px solid var(--border); border-radius: 10px; padding: 0.75rem 1rem; }
  .list a { color: inherit; text-decoration: none; display: grid; grid-template-columns: 1fr auto auto; gap: 0.75rem; align-items: center; }
  .row { display: grid; grid-template-columns: 1fr auto auto; gap: 0.75rem; align-items: center; }
  .status { font-style: normal; font-size: 0.8rem; letter-spacing: 0.02em; }
  .status.completed { color: #3d8b65; }
  .status.processing, .status.pending { color: #b0892a; }
  .status.failed { color: #b04a4a; }
  .empty { color: var(--text-muted); }
  .err { color: #b04a4a; display: block; margin-top: 0.35rem; }
`;
