function formatPercent(percent) {
  const absolute = Math.abs(Number(percent) || 0).toFixed(2);
  const sign = percent > 0 ? "+" : percent < 0 ? "-" : "";
  return `${sign}${absolute}%`;
}

function PerformerCard({ label, performer, toneClassName = "text-[var(--text-secondary)]", selectedRange }) {
  return (
    <article className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/70 px-3.5 py-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}</p>
        <span className="text-[11px] text-[var(--text-secondary)] opacity-70">{selectedRange}</span>
      </div>
      <p className="mt-2 line-clamp-2 text-sm font-semibold text-[var(--text-primary)]">
        {performer?.name || "No qualifying items"}
      </p>
      <p className={`mt-1 text-base font-semibold ${toneClassName}`}>
        {performer ? formatPercent(performer.changePercent) : "-"}
      </p>
    </article>
  );
}

function AllocationCard({ rows = [] }) {
  return (
    <article className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/70 px-3.5 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Portfolio Allocation</p>
      <div className="mt-2.5">
        {rows.length === 0 ? (
          <p className="text-sm text-[var(--text-secondary)]">No allocation data available.</p>
        ) : (
          <div className="grid grid-cols-[minmax(0,1fr)_auto_auto] gap-x-3 gap-y-2 px-0.5">
            <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Category</span>
            <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-right text-[var(--text-secondary)]">Number</span>
            <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-right text-[var(--text-secondary)]">Share</span>

            {rows.flatMap((row) => {
              const countValue = Number.isFinite(Number(row?.count)) ? Number(row.count) : null;
              const rowKey = row.id || row.label;

              return [
                <span key={`${rowKey}-label`} className="min-w-0 truncate text-sm text-[var(--text-primary)]">{row.label}</span>,
                <span key={`${rowKey}-count`} className="text-sm font-semibold text-right tabular-nums text-[var(--text-primary)]">
                  {countValue === null ? "--" : countValue.toLocaleString("en-US")}
                </span>,
                <span key={`${rowKey}-percent`} className="text-sm font-semibold text-right tabular-nums text-[var(--text-primary)]">{row.percent}%</span>,
              ];
            })}
          </div>
        )}
      </div>
    </article>
  );
}

function ConcentrationCard({ concentrationPercent = null }) {
  const isWarning = Number(concentrationPercent) > 50;
  const concentrationTone = isWarning ? "text-amber-300" : "text-[var(--text-primary)]";

  return (
    <article className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/70 px-3.5 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Concentration</p>
      <p className={`mt-2 text-[1.6rem] font-semibold leading-none ${concentrationTone}`}>
        {typeof concentrationPercent === "number" ? `${concentrationPercent}%` : "-"}
      </p>
      <p className="mt-2 text-xs text-[var(--text-secondary)]">
        {typeof concentrationPercent === "number"
          ? `Top 3 assets represent ${concentrationPercent}% of portfolio value.`
          : "Concentration signal will appear once portfolio values are available."}
      </p>
    </article>
  );
}

function parseConcentrationFromText(text) {
  const match = String(text || "").match(/(\d+(?:\.\d+)?)%/);
  if (!match) return null;
  const parsed = Number(match[1]);
  return Number.isFinite(parsed) ? Math.round(parsed) : null;
}

function mapFallbackAllocationRows(signalsData) {
  const rows = Array.isArray(signalsData?.allocationSummary) ? signalsData.allocationSummary : [];
  return rows
    .filter((row) => Number.isFinite(Number(row?.valuePercent)))
    .map((row, index) => ({
      id: row.id || `fallback-allocation-${index}`,
      label: row.label,
      percent: Math.round(Number(row.valuePercent)),
      count: Number.isFinite(Number(row?.count)) ? Number(row.count) : null,
    }));
}

export default function PortfolioSignalsRail({
  performanceHighlights = null,
  selectedRange = "7D",
  portfolioSignals = null,
  signalsData = null,
}) {
  const bestPerformer = performanceHighlights?.bestPerformer || null;
  const worstPerformer = performanceHighlights?.worstPerformer || null;
  const allocationRows = portfolioSignals?.allocationRows?.length
    ? portfolioSignals.allocationRows
    : mapFallbackAllocationRows(signalsData);
  const concentrationPercent = typeof portfolioSignals?.concentrationPercent === "number"
    ? portfolioSignals.concentrationPercent
    : parseConcentrationFromText(signalsData?.concentrationText);

  return (
    <section className="space-y-3">
      <div className="px-1">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">Portfolio Signals</p>
      </div>

      <PerformerCard
        label="Best Performer"
        performer={bestPerformer}
        toneClassName="metric-positive"
        selectedRange={selectedRange}
      />
      <PerformerCard
        label="Worst Performer"
        performer={worstPerformer}
        toneClassName="metric-negative"
        selectedRange={selectedRange}
      />
      <AllocationCard rows={allocationRows} />
      <ConcentrationCard concentrationPercent={concentrationPercent} />
    </section>
  );
}
