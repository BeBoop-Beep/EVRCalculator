/** @typedef {import("@/types/portfolioDashboard").PortfolioInsightsData} PortfolioInsightsData */

/** @type {PortfolioInsightsData} */
const MOCK_INSIGHTS_DATA = {
  topMovers: [
    { id: "m1", name: "Charizard ex SIR", changePercent7d: 8.7, valueLabel: "$582" },
    { id: "m2", name: "Mew ex Gold", changePercent7d: 6.1, valueLabel: "$214" },
    { id: "m3", name: "Gengar VMAX Alt", changePercent7d: -2.4, valueLabel: "$331" },
  ],
  allocationSummary: [
    { id: "a1", label: "Cards", valuePercent: 68, valueLabel: "$12.4k" },
    { id: "a2", label: "Sealed", valuePercent: 24, valueLabel: "$4.4k" },
    { id: "a3", label: "Merchandise", valuePercent: 8, valueLabel: "$1.4k" },
  ],
};

export default function PortfolioInsightsSidebar({ insightsData }) {
  const data = insightsData || MOCK_INSIGHTS_DATA;

  return (
    <div className="space-y-3">
      <section className="dashboard-panel rounded-2xl border border-[var(--border-subtle)] p-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)]">Top Movers</p>
        <div className="mt-3 space-y-2.5">
          {data.topMovers.map((mover) => {
            const deltaClassName = mover.changePercent7d >= 0 ? "metric-positive" : "metric-negative";
            return (
              <div key={mover.id} className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-2.5">
                <div className="flex items-start justify-between gap-3">
                  <p className="line-clamp-1 text-sm font-medium text-[var(--text-primary)]">{mover.name}</p>
                  <p className={`text-xs font-semibold ${deltaClassName}`}>{`${mover.changePercent7d >= 0 ? "+" : ""}${mover.changePercent7d.toFixed(1)}%`}</p>
                </div>
                <p className="mt-1 text-xs text-[var(--text-secondary)]">{mover.valueLabel}</p>
              </div>
            );
          })}
        </div>
      </section>

      <section className="dashboard-panel rounded-2xl border border-[var(--border-subtle)] p-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)]">Allocation Summary</p>
        <div className="mt-3 space-y-2">
          {data.allocationSummary.map((slice) => (
            <div key={slice.id}>
              <div className="mb-1 flex items-center justify-between text-xs text-[var(--text-secondary)]">
                <p>{slice.label}</p>
                <p>{`${slice.valuePercent}%`}</p>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-[var(--surface-page)]">
                <div className="h-full rounded-full bg-brand" style={{ width: `${slice.valuePercent}%` }} />
              </div>
              <p className="mt-1 text-[11px] text-[var(--text-secondary)]">{slice.valueLabel}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
