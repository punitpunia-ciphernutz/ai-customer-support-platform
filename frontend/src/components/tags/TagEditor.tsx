import { FormEvent, useEffect, useId, useMemo, useRef, useState } from "react";
import { cn } from "@/utils/cn";
import { IconChevronDown, IconPlus, IconTrash, IconX } from "@/components/ui/icons";

export const SUGGESTED_TAGS = ["billing", "refund", "login", "bug", "urgent"] as const;

type TagEditorProps = {
  tags: string[];
  suggestions?: string[];
  disabled?: boolean;
  onAdd: (name: string) => void;
  onRemove: (name: string) => void;
  /** Permanently delete tag org-wide (catalog + all entity links). */
  onDeleteGlobal?: (name: string) => void;
  pending?: boolean;
};

export function TagChips({
  tags,
  className,
  emptyLabel = "No tags",
}: {
  tags: string[];
  className?: string;
  emptyLabel?: string;
}) {
  if (!tags.length) {
    return <span className={cn("text-sm text-muted", className)}>{emptyLabel}</span>;
  }
  return (
    <div className={cn("tag-list", className)}>
      {tags.map((tag) => (
        <span key={tag} className="tag-chip">
          {tag}
        </span>
      ))}
    </div>
  );
}

/** Single-tag filter dropdown for inbox/tickets toolbars. */
export function TagFilterDropdown({
  availableTags,
  value,
  onChange,
  className,
}: {
  availableTags: string[];
  value: string | null;
  onChange: (next: string | null) => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const label = value ? value : "All";

  return (
    <div className={cn("tag-filter-dropdown", className)} ref={rootRef}>
      <button
        type="button"
        className={cn("tag-filter-trigger", open && "open", value && "active")}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span>
          Filter by Tag: <strong>{label}</strong>
        </span>
        <IconChevronDown size={14} />
      </button>
      {open && (
        <ul className="tag-filter-menu" role="listbox" aria-label="Filter by tag">
          <li role="option" aria-selected={!value}>
            <button
              type="button"
              className={cn("tag-filter-option", !value && "active")}
              onClick={() => {
                onChange(null);
                setOpen(false);
              }}
            >
              All
            </button>
          </li>
          {availableTags.map((tag) => (
            <li key={tag} role="option" aria-selected={value === tag}>
              <button
                type="button"
                className={cn("tag-filter-option", value === tag && "active")}
                onClick={() => {
                  onChange(tag);
                  setOpen(false);
                }}
              >
                {tag}
              </button>
            </li>
          ))}
          {!availableTags.length && (
            <li className="tag-filter-empty">No tags yet</li>
          )}
        </ul>
      )}
    </div>
  );
}

export function TagEditor({
  tags,
  suggestions = [],
  disabled,
  onAdd,
  onRemove,
  onDeleteGlobal,
  pending,
}: TagEditorProps) {
  const [draft, setDraft] = useState("");
  const [open, setOpen] = useState(false);
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const normalizedTags = useMemo(() => new Set(tags.map((t) => t.toLowerCase())), [tags]);

  const catalogSuggestions = useMemo(() => {
    const merged = new Set<string>([...SUGGESTED_TAGS, ...suggestions]);
    return [...merged].sort();
  }, [suggestions]);

  const addableSuggestions = useMemo(
    () => catalogSuggestions.filter((t) => !normalizedTags.has(t.toLowerCase())),
    [catalogSuggestions, normalizedTags]
  );

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    const onPointerDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
        setDraft("");
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        setDraft("");
      }
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const closePanel = () => {
    setOpen(false);
    setDraft("");
  };

  const submit = (raw: string) => {
    const name = raw.trim().toLowerCase();
    if (!name || normalizedTags.has(name) || disabled || pending) return;
    onAdd(name);
    closePanel();
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit(draft);
  };

  const confirmDeleteGlobal = (tag: string) => {
    if (!onDeleteGlobal || disabled || pending) return;
    const ok = window.confirm(
      `Permanently delete tag “${tag}” everywhere?\n\nThis removes it from the org catalog and from all conversations and tickets.`
    );
    if (ok) onDeleteGlobal(tag);
  };

  return (
    <div className="tag-editor" ref={rootRef}>
      <div className="tag-list">
        {tags.map((tag) => (
          <span key={tag} className="tag-chip tag-chip-editable">
            {tag}
            <button
              type="button"
              className="tag-chip-remove"
              aria-label={`Remove tag ${tag}`}
              disabled={disabled || pending}
              onClick={() => onRemove(tag)}
            >
              <IconX size={12} />
            </button>
          </span>
        ))}
        <button
          type="button"
          className="tag-add-toggle"
          disabled={disabled || pending}
          aria-expanded={open}
          aria-label="Add tag"
          onClick={() => setOpen((v) => !v)}
        >
          <IconPlus size={14} />
          Add Tag
        </button>
      </div>

      {open && (
        <div className="tag-add-panel">
          <form className="tag-add-form" onSubmit={onSubmit}>
            <input
              ref={inputRef}
              className="form-input"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Search or create tag…"
              disabled={disabled || pending}
              aria-label="Add tag"
              list={listId}
            />
            <datalist id={listId}>
              {addableSuggestions.map((t) => (
                <option key={t} value={t} />
              ))}
            </datalist>
            <button
              type="submit"
              className="btn btn-secondary btn-sm"
              disabled={disabled || pending || !draft.trim()}
            >
              Add
            </button>
          </form>

          {catalogSuggestions.length > 0 && (
            <div className="tag-suggestions">
              {catalogSuggestions.map((tag) => {
                const assigned = normalizedTags.has(tag.toLowerCase());
                return (
                  <div key={tag} className="tag-suggestion-row">
                    <button
                      type="button"
                      className={cn("chip", assigned && "active")}
                      disabled={disabled || pending || assigned}
                      onClick={() => submit(tag)}
                    >
                      {tag}
                    </button>
                    {onDeleteGlobal && suggestions.includes(tag) && (
                      <button
                        type="button"
                        className="tag-global-delete"
                        aria-label={`Delete tag ${tag} everywhere`}
                        title="Delete tag everywhere"
                        disabled={disabled || pending}
                        onClick={() => confirmDeleteGlobal(tag)}
                      >
                        <IconTrash size={12} />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
