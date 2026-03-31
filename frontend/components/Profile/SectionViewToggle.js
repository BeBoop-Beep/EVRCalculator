"use client";

/**
 * View toggle for switching between grid and list layouts
 * Only shown if section supports both views
 */
export default function SectionViewToggle({
  currentView = "grid",
  onViewChange = () => {},
  isLoading = false,
}) {
  return (
    <div className="inline-flex gap-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-input)] p-1">
      <button
        onClick={() => onViewChange("grid")}
        disabled={isLoading}
        className={`rounded px-3 py-2 transition-colors disabled:opacity-50 ${
          currentView === "grid"
            ? "bg-[var(--accent)]/10 text-[var(--accent)]"
            : "text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]"
        }`}
        title="Grid view"
      >
        <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
          <path d="M3 3h8v8H3V3zm10 0h8v8h-8V3zM3 13h8v8H3v-8zm10 0h8v8h-8v-8z" />
        </svg>
      </button>
      <button
        onClick={() => onViewChange("list")}
        disabled={isLoading}
        className={`rounded px-3 py-2 transition-colors disabled:opacity-50 ${
          currentView === "list"
            ? "bg-[var(--accent)]/10 text-[var(--accent)]"
            : "text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]"
        }`}
        title="List view"
      >
        <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
          <path d="M3 4h18v2H3V4zm0 7h18v2H3v-2zm0 7h18v2H3v-2z" />
        </svg>
      </button>
    </div>
  );
}
