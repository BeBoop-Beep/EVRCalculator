import PublicOverviewSection from "@/components/Profile/PublicOverviewSection";

export default function PublicPortfolioPerformance({ performance }) {
  const points = performance?.points || [];
  const hasHistory = points.length > 0;

  return (
    <PublicOverviewSection title="Portfolio Performance" subtitle="Public trend view for collection movement.">
      {hasHistory ? (
        <div className="space-y-4">
          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-4">
            <div className="flex h-36 items-end gap-2">
              {points.map((point, index) => (
                <div
                  key={`bar-${index}`}
                  className="flex-1 rounded-t bg-brand/70"
                  style={{ height: `${Math.max(16, point)}%` }}
                />
              ))}
            </div>
            <div className="mt-3 flex items-center justify-between text-xs text-[var(--text-secondary)]">
              <span>{performance.periodLabel}</span>
              <span>{performance.valueLabel}</span>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <MetricCard label="Trend" value={performance.trendLabel} />
            <MetricCard label="Total Return" value={performance.returnLabel} />
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)] p-10 text-center text-sm text-[var(--text-secondary)]">
          No portfolio history has been shared yet.
        </div>
      )}
    </PublicOverviewSection>
  );
}

function MetricCard({ label, value }) {
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">{label}</p>
      <p className="mt-2 text-lg font-semibold text-[var(--text-primary)]">{value}</p>
    </div>
  );
}
