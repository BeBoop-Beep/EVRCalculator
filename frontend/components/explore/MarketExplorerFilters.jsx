"use client";

import { useState } from "react";
import InfoPopover from "@/components/ui/InfoPopover";
import { MARKET_EXPLORER_FILTER_AXES } from "@/lib/explore/marketExplorerState.mjs";
import { formatBasketValue } from "@/lib/explore/marketOverviewPresentation.mjs";

// Explore Segments — the filter workspace.
//
// THREE LIVE AXES. Asset Market selects the parent markets; Sealed Product
// Family and Card Segment select the published submarkets. Era occupies its
// real architectural position but stays explicitly unavailable, because no
// backend publishes an era index — it is a disabled control that says so, never
// a populated dropdown implying analytics exist.
//
// NO SEGMENT IS HARDCODED HERE. Every option is whatever the published payload
// carried, so a segment the backend cannot build simply never appears. Card
// segments are grouped by the parent market they measure, because a Special
// Illustration Rare index over all tracked cards and one over the Top Chase
// cohort are different markets and the user must not have to guess which.
function SegmentOption({ entry, onToggle, isLocked }) {
  const disabled = entry.available !== true || isLocked;
  return (
    <label
      data-market-explorer-filter-option={entry.key}
      data-market-explorer-filter-option-available={entry.available === true ? "true" : "false"}
      className={[
        "flex items-center gap-2 text-xs",
        entry.available === true ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]",
        disabled ? "cursor-default" : "cursor-pointer",
      ].join(" ")}
    >
      <input
        type="checkbox"
        checked={entry.selected === true}
        disabled={disabled}
        onChange={() => onToggle?.(entry.key)}
        className="h-3.5 w-3.5 flex-none rounded-[3px] border-[var(--border-subtle)] bg-transparent accent-[var(--accent)] disabled:opacity-40"
      />
      <span aria-hidden="true" className="inline-block h-2.5 w-2.5 flex-none rounded-[3px]" style={{ backgroundColor: entry.color }} />
      <span className="min-w-0 truncate">{entry.shortLabel || entry.label}</span>
      {entry.available === true
        ? (entry.definition ? <InfoPopover text={entry.definition} /> : null)
        : (
          // Not a bare "Unavailable": a published market the user can see but
          // cannot select has to say why, in the snapshot's own words.
          <span className="ml-auto flex items-center gap-1 flex-none text-[10px] text-[var(--text-secondary)]">
            Unavailable
            {entry.unavailableReason ? <InfoPopover text={entry.unavailableReason} /> : null}
          </span>
        )}
    </label>
  );
}

function UnavailableAxis({ axis, note }) {
  return (
    <div className="mt-2">
      <div
        data-market-explorer-filter-placeholder={axis.id}
        aria-disabled="true"
        className="flex items-center justify-between gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-page)]/25 px-2.5 py-1.5 text-xs text-[var(--text-secondary)]"
      >
        <span className="min-w-0 truncate">{axis.placeholderLabel}</span>
        <span className="flex-none text-[10px] uppercase tracking-[0.07em] opacity-80">{note}</span>
      </div>
    </div>
  );
}

export default function MarketExplorerFilters({
  assetEntries = [],
  sealedEntries = [],
  cardGroups = [],
  reconciliation = null,
  cardReconciliation = null,
  topChaseSegmentStatus = null,
  onToggleMarket,
  onToggleSealedFamily,
  onToggleCardSegment,
  selectedSeriesCount = 0,
}) {
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const axisById = new Map(MARKET_EXPLORER_FILTER_AXES.map((axis) => [axis.id, axis]));
  const hasSealed = sealedEntries.length > 0;
  const hasCards = cardGroups.some((group) => group.entries.length > 0);
  // The chart may never be emptied by selection, so the final remaining series
  // is locked wherever it appears — card, or checkbox.
  const isLocked = (entry) => entry.selected === true && selectedSeriesCount <= 1;

  const body = (
    <div className="space-y-4 px-3 pb-4 sm:px-4">
      <fieldset data-market-explorer-filter-axis="assetMarket" data-market-explorer-filter-available="true" className="min-w-0">
        <legend className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
          {axisById.get("assetMarket").label}
        </legend>
        <ul className="mt-2 space-y-1.5">
          {assetEntries.map((entry) => (
            <li key={entry.key}>
              <SegmentOption entry={entry} onToggle={onToggleMarket} isLocked={isLocked(entry)} />
            </li>
          ))}
        </ul>
      </fieldset>

      <fieldset
        data-market-explorer-filter-axis="cardSegment"
        data-market-explorer-filter-available={hasCards ? "true" : "false"}
        className={hasCards ? "min-w-0" : "min-w-0 opacity-60"}
      >
        <legend className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
          {axisById.get("cardSegment").label}
        </legend>
        {hasCards ? (
          <>
            {cardGroups.map((group) => (
              <div key={group.parentMarket} data-market-explorer-filter-group={group.parentMarket} className="mt-2">
                <p className="text-[10px] font-medium text-[var(--text-secondary)]">{group.label}</p>
                <ul className="mt-1 space-y-1.5">
                  {group.entries.map((entry) => (
                    <li key={entry.key}>
                      <SegmentOption entry={entry} onToggle={onToggleCardSegment} isLocked={isLocked(entry)} />
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            {cardReconciliation?.residualBasketValue ? (
              <p data-market-explorer-card-residual className="mt-2 text-[10px] leading-relaxed text-[var(--text-secondary)]">
                {formatBasketValue(cardReconciliation.residualBasketValue)} of the Raw Card Market sits in{" "}
                {cardReconciliation.residualLabel} and is not published as its own submarket.
              </p>
            ) : null}
            {topChaseSegmentStatus && topChaseSegmentStatus.available !== true ? (
              // Stated rather than silently missing: the reason names the exact
              // authority that does not exist yet.
              // A div, not a p: InfoPopover renders a div, and a div nested in
              // a p is invalid HTML that React reports as a hydration error.
              <div data-market-explorer-chase-segments-unavailable className="mt-2 flex items-start gap-1 text-[10px] leading-relaxed text-[var(--text-secondary)]">
                <span>Chase rarity segments are not published yet.</span>
                <InfoPopover text={topChaseSegmentStatus.reason} />
              </div>
            ) : null}
          </>
        ) : (
          <UnavailableAxis axis={axisById.get("cardSegment")} note="Unavailable" />
        )}
      </fieldset>

      <fieldset
        data-market-explorer-filter-axis="sealedFamily"
        data-market-explorer-filter-available={hasSealed ? "true" : "false"}
        className={hasSealed ? "min-w-0" : "min-w-0 opacity-60"}
      >
        <legend className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
          {axisById.get("sealedFamily").label}
        </legend>
        {hasSealed ? (
          <>
            <ul className="mt-2 space-y-1.5">
              {sealedEntries.map((entry) => (
                <li key={entry.key}>
                  <SegmentOption entry={entry} onToggle={onToggleSealedFamily} isLocked={isLocked(entry)} />
                </li>
              ))}
            </ul>
            {reconciliation?.residualBasketValue ? (
              <p data-market-explorer-sealed-residual className="mt-2 text-[10px] leading-relaxed text-[var(--text-secondary)]">
                {formatBasketValue(reconciliation.residualBasketValue)} of Total Sealed sits in{" "}
                {reconciliation.residualLabel} and is not published as its own submarket.
              </p>
            ) : null}
          </>
        ) : (
          <UnavailableAxis axis={axisById.get("sealedFamily")} note="Unavailable" />
        )}
      </fieldset>

      {/* Architectural position only. The option list is empty by design — a
          populated dropdown here would claim an index nothing computes. */}
      <fieldset
        data-market-explorer-filter-axis="era"
        data-market-explorer-filter-available="false"
        className="min-w-0 opacity-60"
      >
        <legend className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
          {axisById.get("era").label}
        </legend>
        <UnavailableAxis axis={axisById.get("era")} note="Coming soon" />
      </fieldset>
    </div>
  );

  return (
    <section data-market-explorer-filters className="flex min-w-0 flex-col" aria-labelledby="market-explorer-filters-heading">
      <div className="px-3 py-3 sm:px-4">
        <div className="flex items-center gap-2">
          <h2 id="market-explorer-filters-heading" className="text-[16px] font-semibold text-[var(--text-primary)]">
            Explore Segments
          </h2>
          {/* Mobile keeps the workspace compact: the filter list collapses so
              the chart above it is not pushed off-screen by a long checklist. */}
          <button
            type="button"
            data-market-explorer-filters-toggle
            aria-expanded={isMobileOpen}
            aria-controls="market-explorer-filters-body"
            onClick={() => setIsMobileOpen((current) => !current)}
            className="ml-auto rounded-md border border-[var(--border-subtle)] px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.07em] text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/65 desk:hidden"
          >
            {isMobileOpen ? "Hide" : "Filters"}
          </button>
        </div>
        <p className="mt-1 text-xs text-[var(--text-secondary)]">
          Choose which market segments appear on the comparison chart.
        </p>
      </div>
      <div id="market-explorer-filters-body" className={isMobileOpen ? "" : "hidden desk:block"}>
        {body}
      </div>
    </section>
  );
}
