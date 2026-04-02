"use client";

import PortfolioCommandCenter from "@/components/Profile/PortfolioCommandCenter";
import PortfolioPerformanceCanvas from "@/components/Profile/PortfolioPerformanceCanvas";
import PortfolioSignalsRail from "@/components/Profile/PortfolioSignalsRail";

/**
 * Unified Portfolio Overview Composer
 * 
 * Single orchestrator for both private (owner) and public (read-only) portfolio overviews.
 * Handles layout, conditional rendering based on mode, and data flow.
 * 
 * @component
 * @param {Object} props
 * @param {Object} props.dashboardData - Unified dashboard data shape
 * @param {string} props.selectedRange - Currently selected time range (7D, 1M, 6M, 1Y)
 * @param {Function} props.onRangeChange - Callback when range is changed
 * @param {"owner" | "public"} props.mode - Rendering mode (owner = interactive/controls, public = read-only)
 */
export default function PortfolioOverviewComposer({
  dashboardData,
  selectedRange,
  onRangeChange,
  performanceHighlights = null,
  portfolioSignals = null,
  mode = "owner",
}) {
  return (
    <section className="space-y-7">
      <div className="space-y-7">
        {/* Command Center / Snapshot Hero */}
        <PortfolioCommandCenter
          dashboardData={dashboardData}
          mode={mode}
        />

        {/* Dominant flagship analytics surface */}
        <section className="dashboard-panel rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-3 sm:p-4 lg:p-5">
          <div className="grid gap-4 xl:grid-cols-[minmax(0,7fr)_minmax(16rem,3fr)] xl:items-stretch xl:gap-4">
            {/* Performance Chart */}
            <div className="h-full">
              <PortfolioPerformanceCanvas
                performanceData={dashboardData?.performance}
                selectedRange={selectedRange}
                onRangeChange={onRangeChange}
                mode={mode}
              />
            </div>

            {/* Utility Rail */}
            <aside className="space-y-2.5 xl:pt-1">
              <PortfolioSignalsRail
                performanceHighlights={performanceHighlights}
                selectedRange={selectedRange}
                portfolioSignals={portfolioSignals}
                signalsData={dashboardData?.insights}
              />
            </aside>
          </div>
        </section>
      </div>
    </section>
  );
}
