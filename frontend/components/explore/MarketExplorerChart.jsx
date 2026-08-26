"use client";

import { useMemo } from "react";
import MarketExplorerTimeframeSelector from "./MarketOverviewWindowSelector";
import MarketPerformanceChart from "./MarketPerformanceChart";
import {
  MARKET_DIMENSION_LABELS,
  SHARED_COMPARISON_WINDOW_LABEL,
  changeDirection,
  describeChange,
  describeUnavailableWindow,
  formatChangePercent,
  getPricePerformanceChange,
} from "@/lib/explore/marketOverviewPresentation.mjs";
import { buildExplorerChartModel } from "@/lib/explore/marketExplorerSeries.mjs";
import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";

// The Explorer's comparison chart.
//
// It is the SAME chart primitive the Market homepage uses —
// MarketPerformanceChart, with its shared cross-series selection, portalled
// tooltip and keyboard stepping — given a much larger plot box and its own
// legend. No second charting library.
//
// Parent markets and Sealed submarkets are drawn through ONE model
// (buildExplorerChartModel), clipped to the SAME backend-owned comparison span,
// so a submarket line and its parent line can be read against each other. No
// return on this chart is computed in the browser.
//
// The legend names each ACTIVE series and its return over the selected window.
// Series identity is the market's own color; the return's green/red is
// performance semantics only.
const CHART_NOTE = "Chain-linked price performance, base 100. Constituents entering or leaving do not create artificial jumps.";

function toneOf(direction) {
  if (direction === "positive") return POSITIVE_VALUE_COLOR;
  if (direction === "negative") return NEGATIVE_VALUE_COLOR;
  return "var(--text-secondary)";
}

export default function MarketExplorerChart({
  overview,
  selectedSeries = [],
  timeframe,
  timeframeLabel = "",
  timeframeOptions = [],
  onTimeframeChange,
  onToggleSeries,
}) {
  const visibleModel = useMemo(
    () => (timeframe ? buildExplorerChartModel(overview, selectedSeries, timeframe) : null),
    [overview, selectedSeries, timeframe]
  );
  const activeSeries = useMemo(
    () => selectedSeries.filter((series) => series.available !== false),
    [selectedSeries]
  );
  // "All" is the SHARED comparable span, not any one market's tracking start.
  // Saying so on the chart is what keeps it from being read as "Since Tracking".
  const spanLabel = timeframe === "All" ? SHARED_COMPARISON_WINDOW_LABEL : timeframeLabel;

  return (
    <section data-market-explorer-chart-pane className="flex min-w-0 flex-col" aria-labelledby="market-explorer-chart-heading">
      <div className="flex flex-col gap-3 px-3 py-3 sm:px-4 desk:flex-row desk:items-start desk:justify-between desk:gap-6">
        <div className="min-w-0">
          <h2 id="market-explorer-chart-heading" className="text-[16px] font-semibold text-[var(--text-primary)]">
            Market Comparison
          </h2>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">{CHART_NOTE}</p>
          {timeframe === "All" ? (
            <p data-market-explorer-shared-span-note className="mt-1 text-[11px] text-[var(--text-secondary)]">
              All spans the {SHARED_COMPARISON_WINDOW_LABEL.toLowerCase()} — the longest range every selected market shares.
            </p>
          ) : null}
        </div>
        <div className="desk:flex-none">
          <MarketExplorerTimeframeSelector
            options={timeframeOptions}
            value={timeframe}
            onChange={onTimeframeChange}
            ariaDescription="Sets the shared comparison window for the chart and every selected-period return on this page."
          />
        </div>
      </div>

      <ul data-market-explorer-legend className="flex flex-wrap items-center gap-x-5 gap-y-1.5 px-3 pb-3 sm:px-4">
        {activeSeries.map((series) => {
          const change = getPricePerformanceChange(series, timeframe);
          const direction = changeDirection(change);
          return (
            <li key={series.key} data-market-explorer-legend-item={series.key}>
              <button
                type="button"
                data-market-explorer-legend-toggle={series.key}
                aria-pressed="true"
                onClick={() => onToggleSeries?.(series.key)}
                className="inline-flex items-center gap-2 rounded text-xs transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]"
              >
                <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-[3px]" style={{ backgroundColor: series.color }} />
                <span className="text-[var(--text-primary)]">{series.label}</span>
                <span className="font-semibold tabular-nums" style={{ color: toneOf(direction) }}>
                  <span aria-hidden="true">{formatChangePercent(change)}</span>
                  <span className="sr-only">{describeChange(series.label, spanLabel, change, { dimension: MARKET_DIMENSION_LABELS.pricePerformance })}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      <div className="min-w-0 flex-1 px-3 pb-3 sm:px-4">
        {visibleModel?.available
          ? (
            // THE PLOT IS THE PRODUCT, so it gets real height at every width.
            // Previously 256px mobile / 416px desktop, which read as a summary
            // widget rather than the page's central research surface. Stepped
            // responsively rather than one large fixed height: 500px on a
            // laptop would push the rail and the legend off-screen.
            <MarketPerformanceChart
              model={visibleModel}
              plotClassName="h-[21rem] tab:h-[23rem] desk:h-[29rem] 2xl:h-[34rem]"
            />
          )
          : (
            <p role="status" data-market-explorer-chart-unavailable className="py-16 text-center text-sm text-[var(--text-secondary)]">
              {spanLabel ? describeUnavailableWindow(spanLabel) : "Market performance history is unavailable."}
            </p>
          )}
      </div>
    </section>
  );
}
