/**
 * Shared collection statistics bar
 * Displays summary metrics at the top of collection content
 * Used by both My Collection and Public Collection
 *
 * Stats displayed:
 * - Total Cards/Items
 * - Collection Value
 * - Sealed Count (or alternate metric)
 */

export default function CollectionStatBar({
  totalItems = 0,
  totalValue = "$0",
  sealedCount = 0,
  statsConfig = {}, // Allows override of metric labels
  className = "",
}) {
  const metrics = [
    {
      label: statsConfig.itemsLabel || "Total Items",
      value: totalItems,
      hint: statsConfig.itemsHint || "cards, sealed products, and more",
    },
    {
      label: statsConfig.valueLabel || "Collection Value",
      value: totalValue,
      hint: statsConfig.valueHint || "calculated from current market data",
    },
    {
      label: statsConfig.sealedLabel || "Sealed Count",
      value: sealedCount,
      hint: statsConfig.sealedHint || "booster boxes and sealed products",
    },
  ];

  return (
    <div className={`grid gap-3 sm:grid-cols-3 ${className}`}>
      {metrics.map((metric) => (
        <div
          key={metric.label}
          className="dashboard-panel rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-4 text-center"
        >
          <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
            {metric.label}
          </p>
          <p className="mt-2 flex items-center justify-center gap-2 text-2xl font-semibold text-[var(--text-primary)]">
            {typeof metric.value === "number" && metric.value > 0
              ? metric.value.toLocaleString()
              : metric.value}
          </p>
          {metric.hint && (
            <p className="mt-2 text-xs text-[var(--text-secondary)]">{metric.hint}</p>
          )}
        </div>
      ))}
    </div>
  );
}
