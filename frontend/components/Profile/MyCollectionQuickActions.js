export default function MyCollectionQuickActions() {
  return (
    <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5">
      <p className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)]">Quick Actions</p>
      <div className="mt-3 flex flex-wrap gap-2.5">
        <button
          type="button"
          className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] px-4 py-2 text-sm font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
        >
          Add Card
        </button>
        <button
          type="button"
          className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] px-4 py-2 text-sm font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
        >
          Add Sealed Product
        </button>
        <button
          type="button"
          className="rounded-xl border border-[var(--border-subtle)] bg-brand px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-dark"
        >
          Import Collection
        </button>
      </div>
      <p className="mt-3 text-xs text-[var(--text-secondary)]">Owner-only tools for adding and managing inventory.</p>
    </div>
  );
}
