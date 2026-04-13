export default function MyCollectionQuickActions({
  compact = false,
  heroCluster = false,
  onAddCard = () => {},
  onAddSealedProduct = () => {},
  onImportCollection = () => {},
}) {
  const wrapperClasses = heroCluster
    ? "w-full lg:w-auto"
    : compact
    ? "rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-4"
    : "rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5";
  const actionsClasses = heroCluster
    ? "flex flex-wrap gap-2"
    : compact
      ? "mt-3 grid gap-2"
      : "mt-3 flex flex-wrap gap-2.5";
  const buttonClasses = heroCluster
    ? "rounded-xl border border-[var(--border-subtle)] bg-transparent px-3 py-2 text-sm font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
    : compact
    ? "w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-2 text-left text-sm font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
    : "rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] px-4 py-2 text-sm font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]";
  const importButtonClasses = heroCluster
    ? "rounded-xl border border-[var(--border-subtle)] bg-brand px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-dark"
    : compact
      ? "w-full rounded-xl border border-[var(--border-subtle)] bg-brand px-3 py-2 text-left text-sm font-medium text-white transition-colors hover:bg-brand-dark"
      : "rounded-xl border border-[var(--border-subtle)] bg-brand px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-dark";

  return (
    <div className={wrapperClasses}>
      <div className={actionsClasses}>
        <button
          type="button"
          className={buttonClasses}
          onClick={onAddCard}
        >
          Add Card
        </button>
        <button
          type="button"
          className={buttonClasses}
          onClick={onAddSealedProduct}
        >
          Add Sealed Product
        </button>
        <button
          type="button"
          className={importButtonClasses}
          onClick={onImportCollection}
        >
          Import Collection
        </button>
      </div>
      {!heroCluster && (
        <p className="mt-3 text-xs text-[var(--text-secondary)]">Owner-only tools for adding and managing inventory.</p>
      )}
    </div>
  );
}
