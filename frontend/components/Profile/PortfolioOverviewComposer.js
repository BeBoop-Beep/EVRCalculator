"use client";

import PortfolioCommandCenter from "@/components/Profile/PortfolioCommandCenter";
import PortfolioPerformanceCanvas from "@/components/Profile/PortfolioPerformanceCanvas";
import PortfolioInsightsSidebar from "@/components/Profile/PortfolioInsightsSidebar";
import MyCollectionQuickActions from "@/components/Profile/MyCollectionQuickActions";

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
  mode = "owner",
}) {
  const isOwnerMode = mode === "owner";
  const analysisTitle = isOwnerMode ? "Portfolio Intelligence" : "Portfolio Analysis";
  const analysisSubtitle = isOwnerMode
    ? "Track portfolio trajectory with high-signal movers, allocation context, and quick owner actions."
    : "View portfolio performance, top performers, and asset allocation.";

  return (
    <section className="space-y-5">
      {/* Command Center / Snapshot Hero */}
      <PortfolioCommandCenter 
        dashboardData={dashboardData} 
        selectedRange={selectedRange}
        onRangeChange={onRangeChange}
        mode={mode}
      />

      {/* Analytics Dashboard: Performance Chart + Insights Sidebar */}
      <section className="dashboard-panel rounded-2xl border border-[var(--border-subtle)] p-4 sm:p-5 lg:p-6">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">{analysisTitle}</p>
          <h3 className="mt-1 text-lg font-semibold text-[var(--text-primary)]">Performance and Insights</h3>
          <p className="mt-1 text-xs text-[var(--text-secondary)] sm:text-sm">{analysisSubtitle}</p>
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_21rem] xl:items-stretch xl:gap-5">
          {/* Performance Chart */}
          <div className="h-full">
            <PortfolioPerformanceCanvas
              performanceData={dashboardData?.performance}
              selectedRange={selectedRange}
              onRangeChange={onRangeChange}
              mode={mode}
            />
          </div>

          {/* Insights Sidebar */}
          <aside className="space-y-3 xl:pt-0.5">
            {isOwnerMode && (
              <MyCollectionQuickActions compact />
            )}
            <PortfolioInsightsSidebar 
              insightsData={dashboardData?.insights}
              mode={mode}
            />
          </aside>
        </div>
      </section>
    </section>
  );
}
