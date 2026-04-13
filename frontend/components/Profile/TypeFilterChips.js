"use client";

/**
 * Type Filter Chips Component (LAYER 1)
 * Single-selection chip buttons for content type filtering
 * Options: "All", "Cards", "Sealed", "Merchandise"
 */
export default function TypeFilterChips({
  selectedType = "all",
  onTypeChange = () => {},
  isLoading = false,
  availableTypes = [
    { id: "all", label: "All" },
    { id: "cards", label: "Cards" },
    { id: "sealed", label: "Sealed" },
    { id: "merchandise", label: "Merchandise" },
  ],
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {availableTypes.map((type) => (
        <button
          type="button"
          key={type.id}
          onClick={() => onTypeChange(type.id)}
          disabled={isLoading}
          aria-pressed={selectedType === type.id}
          className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${
            selectedType === type.id
              ? "bg-[var(--accent)] text-white"
              : "border border-[var(--border-subtle)] bg-[var(--surface-panel)] text-[var(--text-primary)] hover:bg-[var(--surface-hover)]"
          }`}
        >
          {type.label}
        </button>
      ))}
    </div>
  );
}
