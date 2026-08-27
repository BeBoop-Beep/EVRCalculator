"use client";

import { useMemo } from "react";
import Link from "next/link";
import InfoPopover from "@/components/ui/InfoPopover";
import MarketOverviewWindowSelector from "./MarketOverviewWindowSelector";
import MarketPerformanceChart from "./MarketPerformanceChart";
import {
  buildMarketPerformanceSeries,
  changeDirection,
  describeChange,
  describeUnavailableWindow,
  formatChangePercent,
  formatShortDate,
  getPricePerformanceChange,
  MARKET_DIMENSION_LABELS,
} from "@/lib/explore/marketOverviewPresentation.mjs";
import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";
import styles from "./explore.module.css";
import { ANALYTICAL_ACTION_CLASS, MARKET_EXPLORER_HREF } from "@/components/ui/analyticalInteraction.mjs";

// Deliberately explicit: this chart is the PRICE-PERFORMANCE dimension only.
// Tracked Value (which does move when sets join the universe) lives in the
// Market Overview table beside it and is never plotted here.
//
// The timeframe is CONTROLLED by PokemonMarketAnalysis. This component holds no
// window state of its own — the overview's dynamic period column and this chart
// read one selection, so the two can never disagree about which window is on
// screen. Availability is still decided by the backend, upstream.
const SUB_LABEL = "Chain-linked price performance. New-set additions do not create artificial jumps.";

function toneOf(direction) {
  if (direction === "positive") return POSITIVE_VALUE_COLOR;
  if (direction === "negative") return NEGATIVE_VALUE_COLOR;
  return "var(--text-secondary)";
}

export function filterMarketPerformanceModel(model, visibleMarketKeys) {
  if (!model) return model;
  return {
    ...model,
    series: (model.series || []).filter((series) => visibleMarketKeys?.has(series.key) !== false),
  };
}

export default function PokemonMarketPerformance({ overview, options = [], selectedWindow, selectedLabel = "", onWindowChange, visibleMarketKeys, onToggleMarket, isSinceFirstAvailable = false, displayStartDate = null }) {
  const model = useMemo(
    () => (selectedWindow ? buildMarketPerformanceSeries(overview, selectedWindow) : null),
    [overview, selectedWindow]
  );
  const visibleModel = useMemo(
    () => filterMarketPerformanceModel(model, visibleMarketKeys),
    [model, visibleMarketKeys]
  );

  if (!overview || !overview.families?.length) {
    return null;
  }

  return (
    <section data-market-performance-pane className="flex min-w-0 flex-col" aria-labelledby="market-performance-heading">
      <div className={`${styles.divider} px-3 py-3 sm:px-4`}>
        <div className="flex flex-wrap items-center gap-2">
          <h2 id="market-performance-heading" className="text-[18px] font-semibold text-[var(--text-primary)] desk:text-[15px]">Pokémon Market Performance</h2>
          <span className="desk:hidden"><InfoPopover text={SUB_LABEL} /></span>
          <Link href={MARKET_EXPLORER_HREF} data-market-explorer-cta className={`ml-auto desk:min-h-8 ${ANALYTICAL_ACTION_CLASS}`}>
            Open Market Explorer <span aria-hidden="true">&rarr;</span>
          </Link>
        </div>
        <p id="market-performance-description" className="mt-1 hidden text-xs text-[var(--text-secondary)] desk:block">{SUB_LABEL}</p>
        {/* Legend above, timeframes below. On this pane's ~58% the two do not
            fit on one line, and a selector that wraps mid-row reads as a
            layout accident rather than a design. */}
        <div className="mt-3 flex flex-col gap-2.5">
          <ul data-market-performance-legend className="hidden flex-wrap items-center gap-x-4 gap-y-1.5 desk:flex">
            {overview.families.map((family) => {
              const change = getPricePerformanceChange(family, selectedWindow);
              const direction = changeDirection(change);
              const isVisible = visibleMarketKeys?.has(family.key) !== false;
              return (
                <li key={family.key} data-market-performance-legend-item={family.key}>
                  <button
                    type="button"
                    data-market-performance-toggle={family.key}
                    aria-pressed={isVisible}
                    onClick={() => onToggleMarket?.(family.key)}
                    className={`inline-flex items-center gap-2 rounded text-xs transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)] ${isVisible ? "opacity-100" : "opacity-45"}`}
                  >
                    <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-[3px]" style={{ backgroundColor: family.color }} />
                    <span className="text-[var(--text-primary)]">{family.label}</span>
                    <span className="font-semibold tabular-nums" style={{ color: toneOf(direction) }}>
                      <span aria-hidden="true">{formatChangePercent(change)}</span>
                      <span className="sr-only">{describeChange(family.label, selectedLabel, change, { dimension: MARKET_DIMENSION_LABELS.pricePerformance })}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
          <MarketOverviewWindowSelector
            options={options}
            value={selectedWindow}
            onChange={onWindowChange}
            ariaDescription="Sets the window for both this chart and the Market Overview period column beside it."
          />
          {isSinceFirstAvailable ? (
            <p data-market-performance-coverage-note className="text-[10px] font-medium uppercase tracking-[0.07em] text-[var(--text-secondary)]">
              Since first available{displayStartDate ? ` · ${formatShortDate(displayStartDate)}` : ""}
            </p>
          ) : null}
        </div>
      </div>
      <div className="min-w-0 flex-1 px-3 py-3 sm:px-4">
        {visibleModel?.available
          ? <MarketPerformanceChart model={visibleModel} plotClassName="h-40 desk:h-[13.5rem]" />
          : (
            <p role="status" data-market-performance-unavailable className="py-10 text-center text-sm text-[var(--text-secondary)]">
              {selectedLabel ? describeUnavailableWindow(selectedLabel) : "Market performance history is unavailable."}
            </p>
          )}
      </div>
    </section>
  );
}
