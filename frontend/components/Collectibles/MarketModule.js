export default function MarketModule({ market }) {
  if (!market) return null;

  return (
    <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-5">
      <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Market Intelligence</p>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Metric label="Market Price" value={`$${market.market_price}`} />
        <Metric label="Estimated Value" value={`$${market.estimated_value}`} />
        <Metric label="Liquidity" value={market.liquidity_indicator} />
        <Metric label="Trend Points" value={market.price_trend.join(" -> ")} />
      </div>
      <div className="mt-4 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-3">
        <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Historical Sales</p>
        <ul className="mt-2 space-y-1 text-sm text-[var(--text-primary)]">
          {(market.historical_sales || []).map((sale) => (
            <li key={`${sale.date}-${sale.price}`}>{sale.date}: ${sale.price}</li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function Metric({ label, value }) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-3">
      <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}</p>
      <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">{value}</p>
    </div>
  );
}
