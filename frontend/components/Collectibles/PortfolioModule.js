export default function PortfolioModule({ portfolio, canViewPortfolio }) {
  if (!canViewPortfolio || !portfolio) return null;

  return (
    <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-5">
      <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Portfolio Intelligence</p>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Metric label="Purchase Price" value={`$${portfolio.purchase_price}`} />
        <Metric label="Cost Basis" value={`$${portfolio.cost_basis}`} />
        <Metric label="Current Value" value={`$${portfolio.current_value}`} />
        <Metric label="Unrealized Gain/Loss" value={`$${portfolio.unrealized_gain}`} />
        <Metric label="ROI" value={`${portfolio.roi}%`} />
        <Metric label="Holding Duration" value={`${portfolio.holding_duration_days ?? "-"} days`} />
        <Metric label="Acquisition Date" value={portfolio.acquisition_date || "-"} />
        <Metric label="Quantity" value={portfolio.quantity} />
        <Metric label="Condition" value={portfolio.condition || "-"} />
      </div>
      <div className="mt-4 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-3">
        <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Personal Notes</p>
        <p className="mt-2 text-sm text-[var(--text-primary)]">{portfolio.notes || "No notes"}</p>
      </div>
      <div className="mt-4 flex gap-2">
        <button className="inline-flex items-center rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)]">
          Edit Entry
        </button>
        <button className="inline-flex items-center rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)]">
          Manage Entry
        </button>
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
