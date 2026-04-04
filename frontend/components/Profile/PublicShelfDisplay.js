import CollectionItemCard from "@/components/Profile/CollectionItemCard";

/**
 * Component for displaying sealed products/shelf items in an organized grid.
 * Supports grouping by product type and filtering.
 */
export default function PublicShelfDisplay({
  items = [],
  groupByType = true,
  emptyMessage = "No sealed products available.",
  isLoading = false,
  className = "",
}) {
  if (isLoading) {
    return (
      <div className={`space-y-4 ${className}`}>
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <div
            key={i}
            className="aspect-square animate-pulse rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-hover)]"
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

  // Group items by product type if enabled
  if (groupByType) {
    const groupedItems = items.reduce((acc, item) => {
      const type = item.productType || "Other";
      if (!acc[type]) {
        acc[type] = [];
      }
      acc[type].push(item);
      return acc;
    }, {});

    return (
      <div className={`space-y-8 ${className}`}>
        {Object.entries(groupedItems).map(([type, groupItems]) => (
          <section key={type}>
            <div className="mb-4">
              <h3 className="text-lg font-semibold text-[var(--text-primary)]">{type}</h3>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                {groupItems.length} item{groupItems.length !== 1 ? "s" : ""}
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {groupItems.map((item) => (
                <CollectionItemCard
                  key={item.id}
                  item={item}
                  variant="shelf"
                />
              ))}
            </div>
          </section>
        ))}

        {/* Summary Stats */}
        <div className="grid gap-3 sm:grid-cols-3 border-t border-[var(--border-subtle)] pt-6">
          <StatPill
            label="Total Products"
            value={items.length}
          />
          <StatPill
            label="Categories"
            value={Object.keys(groupedItems).length}
          />
          <StatPill
            label="Shelf Value"
            value="View details"
          />
        </div>
      </div>
    );
  }

  // Ungrouped grid
  return (
    <div className={`grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 ${className}`}>
      {items.map((item) => (
        <CollectionItemCard
          key={item.id}
          item={item}
          variant="shelf"
        />
      ))}
    </div>
  );
}

function StatPill({ label, value }) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-3 text-center">
      <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}</p>
      <p className="mt-1 text-lg font-semibold text-[var(--text-primary)]">{value}</p>
    </div>
  );
}
