"use client";

import { useMemo, useState } from "react";
import MarketOverviewWindowSelector from "./MarketOverviewWindowSelector";
import MarketPerformanceChart from "./MarketPerformanceChart";
import {
  buildMarketPerformanceSeries,
  buildMarketWindowOptions,
  changeDirection,
  describeChange,
  describeUnavailableWindow,
  formatChangePercent,
  getPricePerformanceChange,
  resolveDefaultMarketWindow,
  MARKET_DIMENSION_LABELS,
} from "@/lib/explore/marketOverviewPresentation.mjs";
import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";
import styles from "./explore.module.css";

// Deliberately explicit: this chart is the PRICE-PERFORMANCE dimension only.
// Tracked Value (which does move when sets join the universe) lives in the
// Market Overview table above and is never plotted here.
const SUB_LABEL = "Chain-linked price performance of the Raw Card Market and Top 10 Chase Market. New-set additions do not create artificial jumps.";

function toneOf(direction) {
  if (direction === "positive") return POSITIVE_VALUE_COLOR;
  if (direction === "negative") return NEGATIVE_VALUE_COLOR;
  return "var(--text-secondary)";
}

export default function PokemonMarketPerformance({ overview }) {
  const options = useMemo(() => buildMarketWindowOptions(overview), [overview]);
  const [requestedWindow, setRequestedWindow] = useState(null);
  const defaultWindow = useMemo(() => resolveDefaultMarketWindow(overview, "30D"), [overview]);
  // A selection can only survive while the backend still reports that window
  // available; otherwise fall back to the default rather than charting a span
  // the snapshot does not support.
  const selectedWindow = options.find((entry) => entry.key === requestedWindow && entry.available)
    ? requestedWindow
    : defaultWindow;
  const model = useMemo(
    () => (selectedWindow ? buildMarketPerformanceSeries(overview, selectedWindow) : null),
    [overview, selectedWindow]
  );
  const selectedLabel = options.find((entry) => entry.key === selectedWindow)?.label || "";

  if (!overview || !overview.families?.length) {
    return null;
  }

  return (
    <section className={`${styles.surfaceQuiet} set-glass-surface`} aria-labelledby="market-performance-heading">
      <div className={`${styles.divider} px-3 py-3 sm:px-4`}>
        <h2 id="market-performance-heading" className="text-[18px] font-semibold text-[var(--text-primary)] desk:text-[15px]">Pokémon Market Performance</h2>
        <p id="market-performance-description" className="mt-1 text-xs text-[var(--text-secondary)]">{SUB_LABEL}</p>
        <div className="mt-3 flex flex-col gap-3 desk:flex-row desk:items-center desk:justify-between">
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
            onChange={setRequestedWindow}
            ariaDescription="Clips the chart and the legend change values to the selected published window."
          />
        </div>
      </div>
      <div className="px-3 py-3 sm:px-4">
        {model?.available
          ? <MarketPerformanceChart model={model} />
          : (
            <p role="status" data-market-performance-unavailable className="py-10 text-center text-sm text-[var(--text-secondary)]">
              {selectedLabel ? describeUnavailableWindow(selectedLabel) : "Market performance history is unavailable."}
            </p>
          )}
      </div>
    </section>
  );
}
