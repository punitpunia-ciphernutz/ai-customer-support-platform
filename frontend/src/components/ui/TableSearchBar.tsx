import { IconRefresh, IconSearch } from "@/components/ui/icons";

type TableSearchBarProps = {
  value: string;
  onChange: (value: string) => void;
  onReset?: () => void;
  placeholder?: string;
};

export function TableSearchBar({
  value,
  onChange,
  onReset,
  placeholder = "Search…",
}: TableSearchBarProps) {
  return (
    <div className="table-toolbar">
      <div className="table-search">
        <IconSearch size={16} />
        <input
          className="form-input"
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
      <button
        type="button"
        className="btn btn-ghost btn-sm"
        onClick={() => {
          onChange("");
          onReset?.();
        }}
      >
        <IconRefresh size={14} />
        Reset
      </button>
    </div>
  );
}
