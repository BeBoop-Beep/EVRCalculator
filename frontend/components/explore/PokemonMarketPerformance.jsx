"use client";

import { useMemo } from "react";
import MarketOverviewWindowSelector from "./MarketOverviewWindowSelector";
import MarketPerformanceChart from "./MarketPerformanceChart";
import {
  buildMarketPerformanceSeries,
  changeDirection,
  describeChange,
  describeUnavailableWindow,
  formatChangePercent,
  getPricePerformanceChange,
  MARKET_DIMENSION_LABELS,
} from "@/lib/explore/marketOverviewPresentation.mjs";
import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";
import styles from "./explore.module.css";

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

export default function PokemonMarketPerformance({ overview, options = [], selectedWindow, selectedLabel = "", onWindowChange }) {
  const model = useMemo(
    () => (selectedWindow ? buildMarketPerformanceSeries(overview, selectedWindow) : null),
    [overview, selectedWindow]
  );

  if (!overview || !overview.families?.length) {
    return null;
  }

  return (
    <section data-market-performance-pane className="flex min-w-0 flex-col" aria-labelledby="market-performance-heading">
      <div className={`${styles.divider} px-3 py-3 sm:px-4`}>
        <h2 id="market-performance-heading" className="text-[18px] font-semibold text-[var(--text-primary)] desk:text-[15px]">Pokémon Market Performance</h2>
        <p id="market-performance-description" className="mt-1 text-xs text-[var(--text-secondary)]">{SUB_LABEL}</p>
        {/* Legend above, timeframes below. On this pane's ~58% the two do not
            fit on one line, and a selector that wraps mid-row reads as a
            layout accident rather than a design. */}
        <div className="mt-3 flex flex-col gap-2.5">
          <ul data-market-performance-legend className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
            {overview.families.map((family) => {
              const change = getPricePerformanceChange(family, selectedWindow);
              const direction = changeDirection(change);
              return (
                <li key={family.key} data-market-performance-legend-item={family.key} className="inline-flex items-center gap-2 text-xs">
                  <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-[3px]" style={{ backgroundColor: family.color }} />
                  <span className="text-[var(--text-primary)]">{family.label}</span>
                  <span className="font-semibold tabular-nums" style={{ color: toneOf(direction) }}>
                    <span aria-hidden="true">{formatChangePercent(change)}</span>
                    <span className="sr-only">{describeChange(family.label, selectedLabel, change, { dimension: MARKET_DIMENSION_LABELS.pricePerformance })}</span>
                  </span>
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
        </div>
      </div>
      <div className="min-w-0 flex-1 px-3 py-3 sm:px-4">
        {model?.available
          ? <MarketPerformanceChart model={model} plotClassName="h-48 desk:h-[13.5rem]" />
          : (
            <p role="status" data-market-performance-unavailable className="py-10 text-center text-sm text-[var(--text-secondary)]">
              {selectedLabel ? describeUnavailableWindow(selectedLabel) : "Market performance history is unavailable."}
            </p>
          )}
      </div>
    </section>
  );
}
