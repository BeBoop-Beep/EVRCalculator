"use client";

import { formatIndexValue } from "@/lib/explore/marketOverviewPresentation.mjs";

// The active custom markets, as removable chips.
//
// COMPOSITION LIVES ELSEWHERE. Each query's roster used to render here, which
// meant four added markets produced four large tables stacked down the page.
// It now belongs to the shared Current Constituents panel, which shows ONE
// market at a time and handles cards and sealed products alike. A chip's label
// is the control that points the panel at it.
export default function MarketExplorerDynamicSeries({
  series = [],
  onRemove,
  activeSeriesId = null,
  onInspect,
}) {
  if (!series.length) return null;
  return (
    <section data-market-query-series className="space-y-3" aria-label="Custom comparison markets">
      <ul className="flex flex-wrap gap-2">
        {series.map((entry) => {
          const isActive = entry.key === activeSeriesId;
          return (
            <li
              key={entry.key}
              data-market-query-chip={entry.key}
              data-market-query-chip-asset={entry.asset || "cards"}
              className={[
                "flex items-center gap-2 rounded-lg border bg-[var(--surface-page)]/40 px-3 py-2 text-xs transition-colors",
                isActive ? "border-[rgb(45,212,191)]" : "border-[var(--border-subtle)]",
              ].join(" ")}
            >
              <span aria-hidden="true" className="h-2.5 w-2.5 flex-none rounded-[3px]" style={{ backgroundColor: entry.color }} />
              {/* Inspecting is a separate action from removing: this points the
                  constituent panel at the market, it does not take it off the
                  chart. */}
              <button
                type="button"
                data-market-explorer-inspect={entry.key}
                aria-pressed={isActive}
                onClick={() => onInspect?.(entry.key)}
                className={[
                  "font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]",
                  isActive ? "text-[rgb(45,212,191)]" : "text-[var(--text-primary)] hover:text-[rgb(45,212,191)]",
                ].join(" ")}
              >
                {entry.label}
              </button>
              <span className="tabular-nums text-[var(--text-secondary)]">Index {formatIndexValue(entry.indexValue)}</span>
              <button
                type="button"
                aria-label={`Remove ${entry.label}`}
                onClick={() => onRemove?.(entry.key)}
                className="ml-1 flex h-8 w-8 flex-none items-center justify-center rounded text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)] desk:h-5 desk:w-5"
              >
                ×
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
