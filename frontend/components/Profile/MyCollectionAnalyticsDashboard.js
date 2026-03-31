import MyCollectionQuickActions from "@/components/Profile/MyCollectionQuickActions";
import PortfolioInsightsSidebar from "@/components/Profile/PortfolioInsightsSidebar";
import PortfolioPerformanceCard from "@/components/Profile/PortfolioPerformanceCard";

export default function MyCollectionAnalyticsDashboard({ dashboardData, selectedRange, onRangeChange }) {
  return (
    <section className="dashboard-panel rounded-2xl border border-[var(--border-subtle)] p-4 sm:p-5 lg:p-6">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">Portfolio Intelligence</p>
        <p className="mt-1 text-xs text-[var(--text-secondary)] sm:text-sm">Track portfolio trajectory with high-signal movers, allocation context, and quick owner actions.</p>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_21rem] xl:items-stretch xl:gap-5">
        <div className="h-full">
          <PortfolioPerformanceCard
            performanceData={dashboardData?.performance}
            selectedRange={selectedRange}
            onRangeChange={onRangeChange}
          />
        </div>

        <aside className="space-y-3">
          <MyCollectionQuickActions compact />
          <PortfolioInsightsSidebar insightsData={dashboardData?.insights} />
        </aside>
      </div>
    </section>
  );
}
