import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/services/api/client";
import { Alert, LoadingState, PageHeader } from "@/components/ui";
import { SettingsSubNav } from "@/components/shared/SettingsSubNav";
import { WidgetForm } from "@/features/widgets/WidgetForm";
import { EmbedSnippetCard } from "@/features/widgets/EmbedSnippetCard";
import { WidgetPreview } from "@/features/widgets/WidgetPreview";
import type { ChatWidget, EmbedSnippet, WidgetUpdateInput } from "@/features/widgets/types";
import type { WidgetPreviewDraft } from "@/widget/previewMock";

export function WidgetDetailPage() {
  const { widgetId } = useParams();
  const qc = useQueryClient();
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [previewDraft, setPreviewDraft] = useState<WidgetPreviewDraft | null>(null);
  const onDraftChange = useCallback((draft: WidgetPreviewDraft) => setPreviewDraft(draft), []);

  const widget = useQuery({
    queryKey: ["widgets", widgetId],
    queryFn: () => api<ChatWidget>(`/widgets/${widgetId}`),
    enabled: !!widgetId,
  });

  const snippet = useQuery({
    queryKey: ["widgets", widgetId, "snippet"],
    queryFn: () => api<EmbedSnippet>(`/widgets/${widgetId}/embed-snippet`),
    enabled: !!widgetId,
  });

  const preview = useMutation({
    mutationFn: () =>
      api<{ frame_url: string }>(`/widgets/${widgetId}/preview-token`, { method: "POST" }),
    onSuccess: (data) => {
      const url = new URL(data.frame_url, window.location.origin);
      url.searchParams.set("preview", "true");
      url.searchParams.set("t", String(Date.now()));
      setPreviewUrl(url.toString());
    },
  });

  const save = useMutation({
    mutationFn: (patch: WidgetUpdateInput) =>
      api<ChatWidget>(`/widgets/${widgetId}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      }),
    onSuccess: () => {
      setFormError(null);
      void qc.invalidateQueries({ queryKey: ["widgets"] });
      void qc.invalidateQueries({ queryKey: ["widgets", widgetId] });
      preview.mutate();
    },
    onError: (e) => {
      setFormError(e instanceof ApiError ? e.message : "Save failed");
    },
  });

  useEffect(() => {
    if (widgetId && widget.isSuccess) {
      preview.mutate();
    }
    // Load preview once when widget is available
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [widgetId, widget.isSuccess]);

  if (widget.isLoading) return <LoadingState message="Loading widget…" />;
  if (widget.isError || !widget.data) {
    return (
      <div className="page-scroll">
        <Alert type="error">
          {widget.error instanceof ApiError ? widget.error.message : "Widget not found."}
        </Alert>
        <Link to="/settings/widgets">Back to widgets</Link>
      </div>
    );
  }

  return (
    <div className="page-scroll">
      <PageHeader
        title={widget.data.name}
        description={`Public ID: ${widget.data.public_id}`}
        action={
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <Link to="/settings/widgets" className="btn btn-ghost">
              All widgets
            </Link>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={preview.isPending}
              onClick={() => preview.mutate()}
            >
              {preview.isPending ? "Loading…" : "Refresh preview"}
            </button>
          </div>
        }
      />
      <SettingsSubNav />

      <div className="widget-detail-layout">
        <div className="panel" style={{ padding: "1rem" }}>
          <h3 style={{ marginTop: 0 }}>Configuration</h3>
          <WidgetForm
            key={widget.data.updated_at}
            widget={widget.data}
            saving={save.isPending}
            error={formError}
            onSave={(patch) => save.mutate(patch)}
            onDraftChange={onDraftChange}
          />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {snippet.data && <EmbedSnippetCard snippet={snippet.data} />}
          <WidgetPreview frameUrl={previewUrl} draft={previewDraft} />
        </div>
      </div>
    </div>
  );
}
