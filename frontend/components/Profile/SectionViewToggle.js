"use client";

/**
 * View toggle for switching between collection view modes
 * Supports "continuous" (grid) and "binder" (page-based) layouts
 * Only shown if section supports both views
 */
export default function SectionViewToggle({
  currentView = "continuous",
  onViewChange = () => {},
  isLoading = false,
}) {
  const views = [
    {
      id: "continuous",
      label: "Continuous Scroll",
      icon: (
        <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
          <path d="M3 3h8v8H3V3zm10 0h8v8h-8V3zM3 13h8v8H3v-8zm10 0h8v8h-8v-8z" />
        </svg>
      ),
    },
    {
      id: "binder",
      label: "Binder Pages",
      icon: (
        <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
          <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 9h-4v4h4v-4zm5-9h-4v4h4V3zm0 14h-4v-4h4v4z" />
        </svg>
      ),
    },
  ];

  return (
    <div className="inline-flex gap-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-input)] p-1">
      {views.map((view) => (
        <button
          key={view.id}
          onClick={() => onViewChange(view.id)}
          disabled={isLoading}
          className={`rounded px-3 py-2 transition-colors disabled:opacity-50 ${
            currentView === view.id
              ? "bg-[var(--accent)]/10 text-[var(--accent)]"
              : "text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]"
          }`}
          title={view.label}
        >
          {view.icon}
        </button>
      ))}
    </div>
  );
}
