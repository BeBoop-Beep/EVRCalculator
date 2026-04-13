"use client";

function normalizeLabel(value) {
  if (!value) return "Unknown";
  return String(value)
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function titleCase(value) {
  const normalized = normalizeLabel(value);
  return normalized
    .split(" ")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function FilterGroup({
  title,
  options = [],
  selectedValues = [],
  onToggle = () => {},
  disabled = false,
}) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{title}</p>
      <div className="space-y-1">
        {options.map((option) => {
          const isChecked = selectedValues.includes(option.value);
          return (
            <label
              key={`${title}-${option.value}`}
              className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)]"
            >
              <input
                type="checkbox"
                className="rounded border-[var(--border-subtle)]"
                checked={isChecked}
                disabled={disabled}
                onChange={() => onToggle(option.value)}
              />
              <span>{option.label}</span>
            </label>
          );
        })}
      </div>
    </div>
  );
}

export default function GlobalFilterPanel({
  filters = {},
  options = {},
  onFilterChange = () => {},
  onClearAll = () => {},
  isLoading = false,
}) {
  const tcgSelected = filters.tcg?.length ? filters.tcg : ["All"];
  const setSelected = filters.set || [];
  const conditionSelected = filters.condition || [];
  const eraSelected = filters.era || [];
  const binderSelected = filters.binder || [];
  const assetType = filters.assetType || "all";

  const assetTypeOptions = (options.assetType || [
    { value: "all", label: "All" },
    { value: "cards", label: "Cards" },
    { value: "sealed", label: "Sealed" },
    { value: "merchandise", label: "Merchandise" },
  ]).map((option) => ({
    value: option.value,
    label: option.label,
  }));

  const toggleMulti = (key, value) => {
    const values = filters[key] || [];

    if (value === "All") {
      onFilterChange(key, ["All"]);
      return;
    }

    const withoutAll = values.filter((entry) => entry !== "All");
    const hasValue = withoutAll.includes(value);
    const nextValues = hasValue
      ? withoutAll.filter((entry) => entry !== value)
      : [...withoutAll, value];

    if (key === "tcg") {
      onFilterChange(key, nextValues.length ? nextValues : ["All"]);
      return;
    }

    onFilterChange(key, nextValues);
  };

  const activeCount =
    (tcgSelected.some((v) => v !== "All") ? tcgSelected.filter((v) => v !== "All").length : 0)
    + setSelected.length
    + conditionSelected.length
    + eraSelected.length
    + binderSelected.length
    + (assetType !== "all" ? 1 : 0);

  return (
    <aside className="dashboard-panel rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-4 sm:p-5">
      <div className="space-y-5">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
            Global Filters
          </p>
          {activeCount > 0 ? (
            <button
              type="button"
              onClick={onClearAll}
              disabled={isLoading}
              className="rounded-md border border-[var(--border-subtle)] px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.05em] text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] disabled:opacity-50"
            >
              Clear
            </button>
          ) : null}
        </div>

        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Asset Type</p>
          <div className="grid grid-cols-2 gap-2">
            {assetTypeOptions.map((option) => {
              const isSelected = assetType === option.value;
              return (
                <button
                  key={`asset-${option.value}`}
                  type="button"
                  onClick={() => onFilterChange("assetType", option.value)}
                  disabled={isLoading}
                  className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 ${
                    isSelected
                      ? "bg-[var(--accent)] text-white"
                      : "border border-[var(--border-subtle)] bg-[var(--surface-panel)] text-[var(--text-primary)] hover:bg-[var(--surface-hover)]"
                  }`}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
        </div>

        <FilterGroup
          title="TCG"
          options={(options.tcg || ["All"]).map((value) => ({ value, label: titleCase(value) }))}
          selectedValues={tcgSelected}
          onToggle={(value) => toggleMulti("tcg", value)}
          disabled={isLoading}
        />

        <FilterGroup
          title="Set"
          options={(options.set || []).map((value) => ({ value, label: normalizeLabel(value) }))}
          selectedValues={setSelected}
          onToggle={(value) => toggleMulti("set", value)}
          disabled={isLoading}
        />

        <FilterGroup
          title="Condition"
          options={(options.condition || []).map((value) => ({ value, label: titleCase(value) }))}
          selectedValues={conditionSelected}
          onToggle={(value) => toggleMulti("condition", value)}
          disabled={isLoading}
        />

        <FilterGroup
          title="Era"
          options={(options.era || []).map((value) => ({ value, label: normalizeLabel(value) }))}
          selectedValues={eraSelected}
          onToggle={(value) => toggleMulti("era", value)}
          disabled={isLoading}
        />

        <FilterGroup
          title="Binder"
          options={(options.binder || ["Unassigned"]).map((value) => ({ value, label: normalizeLabel(value) }))}
          selectedValues={binderSelected}
          onToggle={(value) => toggleMulti("binder", value)}
          disabled={isLoading}
        />
      </div>
    </aside>
  );
}