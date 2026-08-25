"use client";

// ---------------------------------------------------------------------------
// ACTIVE MARKETS — one row that answers "what is on this chart right now".
//
// Selections arrive from three places (the quick-segment rail, the Era & Sets
// scope hand-off, Build a Market), and before this row existed the only
// complete answer was to read the legend and cross-reference two collapsed
// groups. Every active series appears here as a chip regardless of where it
// came from.
//
// A chip does TWO things, and they are separate targets:
//   - the chip BODY makes that market the detail target (Current Constituents
//     shows one market at a time, and this is how the user names it);
//   - the × REMOVES it, and nothing re-adds it. There is no automatic parent
//     series any more, so a removed line stays removed.
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
      <div className="flex items-baseline gap-2">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Active Markets</h2>
        <p className="min-w-0 truncate text-[10px] text-[var(--text-secondary)]">
          Select a chip to inspect its constituents.
        </p>
      </div>
      <ul className="flex min-w-0 flex-wrap gap-1.5">
        {series.map((entry) => {
          const isActive = entry.key === activeSeriesId;
          return (
            <li key={entry.key}>
              <span
                data-market-explorer-active-chip={entry.key}
                data-market-explorer-active-chip-selected={isActive ? "true" : "false"}
                className={[
                  "flex min-w-0 max-w-full items-center gap-1.5 rounded-full border px-2 py-1",
                  isActive
                    ? "border-[var(--accent)] bg-[var(--accent)]/12"
                    : "border-[var(--border-subtle)] bg-[var(--surface-page)]/35",
                ].join(" ")}
              >
                <span aria-hidden="true" className="inline-block h-2 w-2 flex-none rounded-full" style={{ backgroundColor: entry.color }} />
                <button
                  type="button"
                  data-market-explorer-active-inspect={entry.key}
                  aria-pressed={isActive}
                  onClick={() => onInspect?.(entry.key)}
                  className="min-w-0 truncate text-[11px] text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/65"
                >
                  {entry.shortLabel || entry.label}
                </button>
                <button
                  type="button"
                  data-market-explorer-active-remove={entry.key}
                  // The chart may never be emptied, so the final chip cannot
                  // remove itself — the same rule the checkboxes enforce.
                  disabled={!canRemove}
                  aria-label={`Remove ${entry.label} from the comparison`}
                  onClick={() => onRemove?.(entry.key)}
                  className="flex-none rounded-full px-1 text-[11px] leading-none text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)] disabled:opacity-35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/65"
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
