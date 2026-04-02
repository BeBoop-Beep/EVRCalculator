/** @typedef {import("@/types/portfolioDashboard").PortfolioInsightsData} PortfolioInsightsData */

/** @type {PortfolioInsightsData} */
const MOCK_INSIGHTS_DATA = {
  topMovers: [
    { id: "m1", name: "Charizard ex SIR", changePercent7d: 8.7, dollarImpact: 51 },
    { id: "m2", name: "Mew ex Gold", changePercent7d: 6.1, dollarImpact: 13 },
    { id: "m3", name: "Gengar VMAX Alt", changePercent7d: -2.4, dollarImpact: -8 },
  ],
  allocationSummary: [],
};

function formatImpact(dollarImpact) {
  if (dollarImpact == null) return null;
  const abs = Math.abs(dollarImpact);
  const sign = dollarImpact >= 0 ? "+" : "-";
  const formatted = abs >= 1000 ? `$${(abs / 1000).toFixed(1)}k` : `$${abs}`;
  return `${sign}${formatted} impact`;
}

/**
 * Portfolio Movers
 *
 * Displays the top portfolio assets driving change over the active time range.
 * Sorted by absolute dollar impact on total portfolio value.
 *
 * @component
 * @param {Object} props
 * @param {Object} props.insightsData - Insights data containing topMovers
 * @param {string} [props.selectedRange="7D"] - Active time range label (7D, 1M, 6M, 1Y)
 */
export default function PortfolioInsightsSidebar({ insightsData, selectedRange = "7D" }) {
  const data = insightsData || MOCK_INSIGHTS_DATA;
  const movers = (data.topMovers || []).slice(0, 3);

  return (
    <section className="dashboard-panel rounded-2xl border border-[var(--border-subtle)] p-4">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)]">
          Portfolio Movers
        </p>
        <span className="text-[11px] font-medium text-[var(--text-secondary)] opacity-60">{selectedRange}</span>
      </div>

      {movers.length === 0 ? (
        <p className="mt-3 text-xs text-[var(--text-secondary)]">No mover data available.</p>
      ) : (
        <div className="mt-3 space-y-2.5">
          {movers.map((mover) => {
            const isPositive = mover.changePercent7d >= 0;
            const deltaClassName = isPositive ? "metric-positive" : "metric-negative";
            const impactLabel = formatImpact(mover.dollarImpact);

            return (
              <div
                key={mover.id}
                className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3.5 py-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="line-clamp-1 text-sm font-medium text-[var(--text-primary)]">
                    {mover.name}
                  </p>
                  <p className={`shrink-0 text-xs font-semibold ${deltaClassName}`}>
                    {`${isPositive ? "+" : ""}${mover.changePercent7d.toFixed(1)}%`}
                  </p>
                </div>
                {impactLabel && (
                  <p className={`mt-1 text-xs font-medium ${deltaClassName}`}>{impactLabel}</p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
