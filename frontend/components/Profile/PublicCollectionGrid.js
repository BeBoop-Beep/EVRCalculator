import CollectionItemCard from "@/components/Profile/CollectionItemCard";

/**
 * Reusable grid component for displaying collection items.
 * Supports different view modes and filtering/sorting hooks.
 */
export default function PublicCollectionGrid({
  items = [],
  emptyMessage = "No items to display.",
  variant = "compact", // compact, detailed
  viewMode = "grid", // grid, list
  isLoading = false,
  className = "",
}) {
  if (isLoading) {
    return (
      <div className={`space-y-4 ${className}`}>
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <div
            key={i}
            className="aspect-[16/10] animate-pulse rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-hover)]"
          />
        ))}
      </div>
    );
  }

  if (!items || items.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)] p-12 text-center">
        <p className="text-sm text-[var(--text-secondary)]">{emptyMessage}</p>
      </div>
    );
  }

  const gridClass = {
    grid: `grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 ${className}`,
    list: `space-y-3 ${className}`,
  }[viewMode];

  if (viewMode === "list") {
    return (
      <div className={gridClass}>
        {items.map((item) => (
          <div
            key={item.id}
            className="flex gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-3"
          >
            <div className="h-20 w-20 shrink-0 overflow-hidden rounded-lg bg-[var(--surface-hover)]">
              {item.imageUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={item.imageUrl}
                  alt={item.name}
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="flex h-full items-center justify-center text-xs text-[var(--text-secondary)]">
                  No img
                </div>
              )}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-[var(--text-primary)]">{item.name}</p>
              <p className="text-xs text-[var(--text-secondary)]">{item.context}</p>
              {item.valueLabel && (
                <p className="mt-2 text-sm font-medium text-[var(--text-primary)]">{item.valueLabel}</p>
              )}
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className={gridClass}>
      {items.map((item) => (
        <CollectionItemCard
          key={item.id}
          item={item}
          variant={variant}
        />
      ))}
    </div>
  );
}
