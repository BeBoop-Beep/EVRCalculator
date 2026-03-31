export default function MyCollectionQuickActions({ compact = false }) {
  const wrapperClasses = compact
    ? "rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-4"
    : "rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5";
  const actionsClasses = compact ? "mt-3 grid gap-2" : "mt-3 flex flex-wrap gap-2.5";
  const buttonClasses = compact
    ? "w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-2 text-left text-sm font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
    : "rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] px-4 py-2 text-sm font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]";

  return (
    <div className={wrapperClasses}>
      <p className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)]">Quick Actions</p>
      <div className={actionsClasses}>
        <button
          type="button"
          className={buttonClasses}
        >
          Add Card
        </button>
        <button
          type="button"
          className={buttonClasses}
        >
          Add Sealed Product
        </button>
        <button
          type="button"
          className={compact
            ? "w-full rounded-xl border border-[var(--border-subtle)] bg-brand px-3 py-2 text-left text-sm font-medium text-white transition-colors hover:bg-brand-dark"
            : "rounded-xl border border-[var(--border-subtle)] bg-brand px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-dark"
          }
        >
          Import Collection
        </button>
      </div>
      <p className="mt-3 text-xs text-[var(--text-secondary)]">Owner-only tools for adding and managing inventory.</p>
    </div>
  );
}
