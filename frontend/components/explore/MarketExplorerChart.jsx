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
      <div className="px-3 py-3 sm:px-4">
        <h2 id="market-explorer-chart-heading" className="sr-only">Market performance chart</h2>
        <div data-market-explorer-chart-toolbar className="flex flex-col gap-2 desk:flex-row desk:items-center desk:gap-4">
          <MarketChartViewToggle value={viewMode} onChange={setViewMode} />
          <div className="flex min-w-0 flex-1 items-center justify-end gap-2 overflow-x-auto pb-1 desk:overflow-visible desk:pb-0">
            <MarketExplorerTimeframeSelector
              options={timeframeOptions}
              value={timeframe}
              onChange={onTimeframeChange}
              ariaDescription="Sets the timeframe for the chart and every selected-period return on this page. Each market is measured over its own history. Changing it does not change which markets are on the chart."
            />
            <button
              type="button"
              data-market-explorer-clear-graph
              onClick={onClearGraph}
              disabled={!totalActiveCount}
              aria-label="Clear Graph: remove every active market from the chart"
              className="flex-none rounded-md px-2 py-1 text-[11px] font-medium text-[var(--text-secondary)] transition-colors hover:bg-[rgba(248,113,113,0.06)] hover:text-[rgb(248,113,113)] disabled:opacity-25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]"
            >
              Clear Graph
            </button>
          </div>
          {timeframe === "All" ? <span data-market-explorer-all-span-note className="sr-only">All shows each selected market since its own tracking start.</span> : null}
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
              plotClassName="h-[30rem] tab:h-[38rem] desk:h-[calc(100vh-12.5rem)] desk:min-h-[40rem] desk:max-h-[54rem] 2xl:h-[calc(100vh-11.5rem)]"
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
