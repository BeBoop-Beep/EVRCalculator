import CollectionItemCard from "@/components/Profile/CollectionItemCard";

/**
 * Component for displaying a collector's public wishlist.
 * Shows wanted items with priority indicators and value estimates.
 */
export default function PublicWishlistDisplay({
  items = [],
  emptyMessage = "No wishlist items shared.",
  priorityGroups = true,
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

  // Group by priority if enabled
  if (priorityGroups) {
    const priorityMap = {
      high: [],
      medium: [],
      low: [],
    };

    items.forEach((item) => {
      const priority = item.priority || "medium";
      if (priorityMap[priority]) {
        priorityMap[priority].push(item);
      }
    });

    return (
      <div className={`space-y-8 ${className}`}>
        {/* High Priority */}
        {priorityMap.high.length > 0 && (
          <WishlistSection
            title="High Priority"
            subtitle="Actively seeking these items"
            items={priorityMap.high}
            priority="high"
          />
        )}

        {/* Medium Priority */}
        {priorityMap.medium.length > 0 && (
          <WishlistSection
            title="Medium Priority"
            subtitle="Interested in these items"
            items={priorityMap.medium}
            priority="medium"
          />
        )}

        {/* Low Priority */}
        {priorityMap.low.length > 0 && (
          <WishlistSection
            title="Low Priority"
            subtitle="Nice to have items"
            items={priorityMap.low}
            priority="low"
          />
        )}

        {/* Summary */}
        <div className="grid gap-3 border-t border-[var(--border-subtle)] pt-6 sm:grid-cols-3">
          <StatPill
            label="Total Wishlist Items"
            value={items.length}
          />
          <StatPill
            label="Estimated Value"
            value={
              items.reduce((sum, item) => {
                const val = parseInt(item.estimatedValue || 0);
                return sum + val;
              }, 0)
            }
          />
          <StatPill
            label="Categories"
            value={new Set(items.map((i) => i.tcg || "Other")).size}
          />
        </div>
      </div>
    );
  }

  // Ungrouped grid
  return (
    <div className={`grid gap-4 sm:grid-cols-2 lg:grid-cols-3 ${className}`}>
      {items.map((item) => (
        <CollectionItemCard
          key={item.id}
          item={item}
          variant="detailed"
        />
      ))}
    </div>
  );
}

function WishlistSection({ title, subtitle, items, priority }) {
  const priorityColors = {
    high: "bg-red-500/10 border-red-500/20",
    medium: "bg-amber-500/10 border-amber-500/20",
    low: "bg-blue-500/10 border-blue-500/20",
  };

  return (
    <section className={`rounded-xl border p-5 ${priorityColors[priority] || ""}`}>
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-[var(--text-primary)]">{title}</h3>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">{subtitle}</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item) => (
          <CollectionItemCard
            key={item.id}
            item={item}
            variant="detailed"
          />
        ))}
      </div>
    </section>
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
