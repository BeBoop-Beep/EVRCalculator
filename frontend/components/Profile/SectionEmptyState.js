/**
 * Empty state for collection sections
 * Shows when no items match filters/search or section is empty
 */
export default function SectionEmptyState({
  title = "No items",
  description = "Add items to get started.",
  icon = "📦",
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] py-16 px-6 text-center">
      <div className="mb-4 text-4xl">{icon}</div>
      <p className="text-lg font-semibold text-[var(--text-primary)]">{title}</p>
      <p className="mt-2 max-w-sm text-sm text-[var(--text-secondary)]">
        {description}
      </p>
    </div>
  );
}
