"use client";

import { useMemo, useState } from "react";
import MarketExplorerTimeframeSelector from "./MarketOverviewWindowSelector";
import MarketChartViewToggle from "./MarketChartViewToggle";
import MarketPerformanceChart from "./MarketPerformanceChart";
import { MARKET_CHART_VIEW_INDEX, MARKET_CHART_VIEW_PERFORMANCE } from "./marketPerformanceDomain.mjs";
import {
  describeUnavailableWindow,
} from "@/lib/explore/marketOverviewPresentation.mjs";
import { buildExplorerChartModel } from "@/lib/explore/marketExplorerSeries.mjs";

// The Explorer's comparison chart.
//
// It is the SAME chart primitive the Market homepage uses —
// MarketPerformanceChart, with its shared cross-series selection, portalled
// tooltip and keyboard stepping — given a much larger plot box and its own
// legend. No second charting library.
//
// Parent markets and Sealed submarkets are drawn through ONE model
// (buildExplorerChartModel), each clipped to ITS OWN backend-owned window, so
// a submarket line and its parent line can be read against each other and each
// legend number describes exactly the span its line covers. No return on this
// chart is computed in the browser.
//
// The legend names each ACTIVE series and its return over the selected window.
// Series identity is the market's own color; the return's green/red is
// performance semantics only.
const PERFORMANCE_NOTE = "Selected-window performance. Each market starts at 0% at its first available observation; canonical Market Index remains available in the tooltip.";
const INDEX_NOTE = "Canonical Market Index. Timeframe changes which dates are shown; index levels remain based on each market's lifetime chain-linked history.";

export default function MarketExplorerChart({
  overview,
  selectedSeries = [],
  totalActiveCount = selectedSeries.length,
  timeframe,
  timeframeLabel = "",
  timeframeOptions = [],
  onTimeframeChange,
  onClearGraph,
}) {
  const [viewMode, setViewMode] = useState(MARKET_CHART_VIEW_PERFORMANCE);
  const visibleModel = useMemo(
    () => (timeframe ? buildExplorerChartModel(overview, selectedSeries, timeframe) : null),
    [overview, selectedSeries, timeframe]
  );
  // "All" is each series' OWN tracked history, so the spoken span label is
  // simply the selected timeframe. It is deliberately NOT the shared
  // comparable span any more — that analytic survives in the payload but is
  // never presented under a timeframe button.
  const spanLabel = timeframeLabel;

  return (
    <section data-market-explorer-chart-pane className="flex min-w-0 flex-col" aria-labelledby="market-explorer-chart-heading">
      <div className="flex flex-col gap-3 px-3 py-3 sm:px-4 desk:flex-row desk:items-start desk:justify-between desk:gap-6">
        <div className="min-w-0">
          <h2 id="market-explorer-chart-heading" className="sr-only">Market performance chart</h2>
          <p className="text-[10px] text-[var(--text-secondary)]">{viewMode === MARKET_CHART_VIEW_INDEX ? INDEX_NOTE : PERFORMANCE_NOTE}</p>
          {timeframe === "All" ? (
            <p data-market-explorer-all-span-note className="mt-1 text-[11px] text-[var(--text-secondary)]">
              All shows each selected market since its own tracking start, so lines may begin on different dates.
            </p>
          ) : null}
        </div>
        <div className="flex flex-col items-stretch gap-2 desk:flex-none desk:items-end">
          <MarketChartViewToggle value={viewMode} onChange={setViewMode} />
          <MarketExplorerTimeframeSelector
            options={timeframeOptions}
            value={timeframe}
            onChange={onTimeframeChange}
            ariaDescription="Sets the timeframe for the chart and every selected-period return on this page. Each market is measured over its own history. Changing it does not change which markets are on the chart."
          />
          {/* GRAPH-LEVEL controls. Distinct from Builder Clear (which lives with
              the Builder and only resets the draft): these three act on what is
              CURRENTLY ON THE CHART. Show all / Hide all is one click instead of
              toggling every series individually; Clear Graph removes every
              active market outright and never re-adds a default. */}
          <div
            data-market-explorer-graph-controls
            role="group"
            aria-label="Graph controls"
            className="flex flex-wrap items-center gap-1.5 text-[11px]"
          >
            <button
              type="button"
              data-market-explorer-clear-graph
              onClick={onClearGraph}
              disabled={!totalActiveCount}
              aria-label="Clear Graph: remove every active market from the chart"
              className="rounded-full border border-[var(--border-subtle)] px-2.5 py-1 font-medium text-[var(--text-secondary)] transition-colors hover:border-[rgba(248,113,113,0.5)] hover:text-[rgb(248,113,113)] disabled:opacity-35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]"
            >
              Clear Graph
            </button>
          </div>
        </div>
      </div>

      {totalActiveCount === 0 ? (
        <p role="status" data-market-explorer-no-active-markets className="px-3 pb-2 text-[11px] text-[var(--text-secondary)] sm:px-4">
          No active markets. Select a market above or build one to add a line to the chart.
        </p>
      ) : selectedSeries.length === 0 ? (
        <p role="status" data-market-explorer-all-hidden className="px-3 pb-2 text-[11px] text-[var(--text-secondary)] sm:px-4">
          Every active market is hidden. Use &quot;Show all&quot; or toggle one on in Active Markets below.
        </p>
      ) : null}

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
              timeframe={timeframe}
              viewMode={viewMode}
              plotClassName="h-[24rem] tab:h-[30rem] desk:h-[38rem] 2xl:h-[42rem]"
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
