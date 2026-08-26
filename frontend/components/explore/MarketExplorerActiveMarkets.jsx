"use client";

import { formatIndexValue } from "@/lib/explore/marketOverviewPresentation.mjs";

// ---------------------------------------------------------------------------
// ACTIVE MARKETS — the ONE answer to "what is on this chart right now".
//
// IT USED TO BE TWO. This row rendered every active series, and directly
// beneath it a second strip re-rendered the custom-query subset with its own
// chips, its own remove buttons and its own inspect targets. Two controls for
// one fact meant a query could be removed from one place and still look present
// in the other, and the page read as though it were repeating itself. The
// second strip is gone; its one genuinely useful contribution — showing a
// custom market's index level, which has no card elsewhere on the page — was
// absorbed into the chip below. NO FUNCTIONALITY WAS DROPPED.
//
// A chip does TWO things, and they are separate targets:
//   - the chip BODY makes that market the detail target (Current Constituents
//     shows one market at a time, and this is how the user names it);
//   - the × REMOVES it, and nothing re-adds it. There is no automatic parent
//     series any more, so a removed line stays removed.
//
// TWO STATES, NOT ONE. Every chip shown is ACTIVE IN CHART. Exactly one is also
// SELECTED FOR DETAIL, and that one carries the green interaction treatment —
// the same green as a selected rail row, a focused search field and the primary
// CTA. Yellow is not used: it is the scarce emphasis color, not the generic
// selection color.
//
// The series marker stays IDENTITY. A selected chip is a green chip carrying
// its market's own color, never a chip repainted in its market's color.
// ---------------------------------------------------------------------------
export default function MarketExplorerActiveMarkets({
  series = [],
  activeSeriesId = null,
  onInspect,
  onRemove,
  canRemove = true,
}) {
  if (!series.length) return null;
  return (
    <section
      data-market-explorer-active-markets
      data-market-explorer-active-count={series.length}
      className="flex min-w-0 flex-col gap-2 px-3 py-3 sm:px-4"
      aria-label="Active markets"
    >
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Active Markets</h2>
        <p className="min-w-0 text-[10px] text-[var(--text-secondary)]">
          All are on the chart. Select one to inspect its constituents.
        </p>
      </div>
      <ul className="flex min-w-0 flex-wrap gap-1.5">
        {series.map((entry) => {
          const isActive = entry.key === activeSeriesId;
          // Custom markets have no summary card anywhere else on the page, so
          // their index level rides on the chip. Prepared markets already have
          // a card and would only be repeating themselves.
          const showsIndexValue = Boolean(entry.queryKey) && entry.indexValue !== undefined;
          return (
            <li key={entry.key}>
              <span
                data-market-explorer-active-chip={entry.key}
                data-market-explorer-active-chip-selected={isActive ? "true" : "false"}
                data-market-explorer-active-chip-asset={entry.asset || undefined}
                data-market-explorer-active-chip-source={entry.queryKey ? "query" : "prepared"}
                className={[
                  "flex min-w-0 max-w-full items-center gap-1.5 rounded-full border px-2 py-1 transition-colors",
                  isActive
                    ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,0.12)] shadow-[inset_0_0_0_1px_rgba(45,212,191,0.15)]"
                    : "border-[var(--border-subtle)] bg-[var(--surface-page)]/35 hover:border-[rgba(45,212,191,0.38)]",
                ].join(" ")}
              >
                <span aria-hidden="true" className="inline-block h-2 w-2 flex-none rounded-full" style={{ backgroundColor: entry.color }} />
                <button
                  type="button"
                  data-market-explorer-active-inspect={entry.key}
                  aria-pressed={isActive}
                  onClick={() => onInspect?.(entry.key)}
                  className={[
                    "min-w-0 truncate text-[11px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]",
                    isActive ? "font-semibold text-[rgb(45,212,191)]" : "text-[var(--text-primary)]",
                  ].join(" ")}
                >
                  {entry.shortLabel || entry.label}
                </button>
                {showsIndexValue ? (
                  <span data-market-explorer-active-chip-index={entry.key} className="flex-none tabular-nums text-[10px] text-[var(--text-secondary)]">
                    {formatIndexValue(entry.indexValue)}
                  </span>
                ) : null}
                <button
                  type="button"
                  data-market-explorer-active-remove={entry.key}
                  // The chart may never be emptied, so the final chip cannot
                  // remove itself — the same rule the checkboxes enforce.
                  disabled={!canRemove}
                  aria-label={`Remove ${entry.label} from the comparison`}
                  onClick={() => onRemove?.(entry.key)}
                  className="flex-none rounded-full px-1 text-[11px] leading-none text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)] disabled:opacity-35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]"
                >
                  ×
                </button>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
