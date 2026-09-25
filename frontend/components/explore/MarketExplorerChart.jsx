"use client";

import { Fragment, useMemo, useState } from "react";
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
  detailsOpen = false,
  onToggleDetails,
  // The trigger is offered whenever at least one market is active (see client).
  constituentsAvailable = true,
  // FOCUS MODE (presentation only). null = comparison mode; a market key = that
  // market keeps its colour and the other visible lines recede.
  focusedSeriesKey = null,
  onClearFocus,
  // ARCHITECTURAL SEAM for future analytical focus tools. Capability-driven:
  // each entry is { id, render: ({ focusedSeries }) => node }. The strip renders
  // whatever the caller supplies; nothing is hard-coded here and none is
  // exposed today.
  focusTools = [],
  // The Explorer chart is an OPEN CANVAS by default: no enclosing card, no plot
  // border, no interior background. /Market keeps the card surface because it
  // never passes `minimal`.
  openCanvas = true,
}) {
  const [viewMode, setViewMode] = useState(MARKET_CHART_VIEW_INDEX);
  const visibleModel = useMemo(
    () => (timeframe ? buildExplorerChartModel(overview, selectedSeries, timeframe) : null),
    [overview, selectedSeries, timeframe]
  );
  // "All" is each series' OWN tracked history, so the spoken span label is
  // simply the selected timeframe. It is deliberately NOT the shared
  // comparable span any more — that analytic survives in the payload but is
  // never presented under a timeframe button.
  const spanLabel = timeframeLabel;
  const focusedSeries = focusedSeriesKey ? selectedSeries.find((entry) => entry.key === focusedSeriesKey) || null : null;

  return (
    <section data-market-explorer-chart-pane className="flex min-w-0 flex-col" aria-labelledby="market-explorer-chart-heading">
      <div className="px-2 pb-1 pt-2 sm:px-3">
        <h2 id="market-explorer-chart-heading" className="sr-only">Market performance chart</h2>
        <div data-market-explorer-chart-toolbar className="flex flex-col gap-2 desk:flex-row desk:items-center desk:justify-between desk:gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <MarketChartViewToggle value={viewMode} onChange={setViewMode} />
          </div>
          <div className="min-w-0 overflow-x-auto pb-1 desk:ml-auto desk:overflow-visible desk:pb-0">
            <MarketExplorerTimeframeSelector
              options={timeframeOptions}
              value={timeframe}
              onChange={onTimeframeChange}
              ariaDescription="Sets the timeframe for the chart and every selected-period return on this page. Each market is measured over its own history. Changing it does not change which markets are on the chart."
            />
          </div>
        </div>
        <div className="mt-1 flex items-start gap-3 border-t border-[var(--border-subtle)] pt-1.5">
          <div className="min-w-0 flex-1">
          <p className="text-[10px] text-[var(--text-secondary)]">{viewMode === MARKET_CHART_VIEW_INDEX ? INDEX_NOTE : PERFORMANCE_NOTE}</p>
          {timeframe === "All" ? (
            <p data-market-explorer-all-span-note className="mt-1 text-[11px] text-[var(--text-secondary)]">
              All shows each selected market since its own tracking start, so lines may begin on different dates.
            </p>
          ) : null}
          </div>
        </div>
      </div>

      {focusedSeries ? (
        <div
          data-market-explorer-focus-strip
          role="group"
          aria-label="Focus mode"
          className="mx-2 mb-1 flex flex-wrap items-center gap-2 rounded-md border border-sky-400/40 bg-sky-400/[.08] px-2.5 py-1.5 text-[11px] sm:mx-3"
        >
          <span data-market-explorer-focus-label className="min-w-0 truncate font-semibold text-sky-100">
            Focused: {focusedSeries.label}
          </span>
          <button
            type="button"
            data-market-explorer-clear-focus
            onClick={onClearFocus}
            className="min-h-8 rounded-md border border-sky-300/50 px-2.5 font-semibold text-sky-100 transition-colors hover:bg-sky-400/[.16] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300/80"
          >
            Clear Focus
          </button>
          {focusTools.map((tool) => <Fragment key={tool.id}>{tool.render({ focusedSeries })}</Fragment>)}
        </div>
      ) : null}

      {totalActiveCount === 0 ? (
        <p role="status" data-market-explorer-no-active-markets className="px-2 pb-1 text-[11px] text-[var(--text-secondary)] sm:px-3">
          No active markets. Select a market above or build one to add a line to the chart.
        </p>
      ) : selectedSeries.length === 0 ? (
        <p role="status" data-market-explorer-all-hidden className="px-2 pb-1 text-[11px] text-[var(--text-secondary)] sm:px-3">
          Every active market is hidden. Use &quot;Show all&quot; or toggle one on in Active Markets below.
        </p>
      ) : null}

      <div className="min-w-0 flex-1 pl-2 pr-3 sm:pl-3 sm:pr-4">
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
              plotClassName="h-[20rem] tab:h-[26rem] desk:h-[clamp(19rem,calc(100dvh-24rem),42rem)]"
              minimal={openCanvas}
              focusedSeriesKey={focusedSeries ? focusedSeries.key : null}
            />
          )
          : (
            <p role="status" data-market-explorer-chart-unavailable className="py-16 text-center text-sm text-[var(--text-secondary)]">
              {spanLabel ? describeUnavailableWindow(spanLabel) : "Market performance history is unavailable."}
            </p>
          )}
      </div>

      {/* BOTTOM-CENTER ANALYSIS ACTION. Lives inside the chart pane directly under
          the x-axis dates, so it is part of the chart workspace (visible without
          scrolling, centred on the plot) rather than the toolbar or a page section.
          It opens the in-place takeover overlay; violet marks it as an analysis
          action, distinct from performance green/red and selected-teal controls. */}
      <div data-market-explorer-chart-bottom-actions className="flex flex-none justify-center px-2 pb-2 pt-1.5 sm:px-3">
        {constituentsAvailable ? <button
          type="button"
          data-market-explorer-view-details
          aria-expanded={detailsOpen}
          onClick={onToggleDetails}
          className="min-h-10 rounded-lg border border-violet-400/60 bg-violet-500/[.12] px-4 text-xs font-semibold text-violet-200 shadow-[0_0_16px_rgba(139,92,246,0.35)] transition-colors hover:border-violet-300/85 hover:bg-violet-500/[.24] hover:text-violet-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300/80 focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--surface-page)]"
        >
          View Constituents &amp; Comparison
        </button> : null}
      </div>
    </section>
  );
}
