import PublicOverviewSection from "@/components/Profile/PublicOverviewSection";

export default function PublicPortfolioSnapshot({ stats = [] }) {
  return (
    <PublicOverviewSection title="Portfolio Snapshot" subtitle="High-level collection metrics.">
      {stats.length === 0 ? (
        <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)] p-8 text-sm text-[var(--text-secondary)]">
          Snapshot metrics are not available yet.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {stats.map((stat) => (
            <div key={stat.id} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">{stat.label}</p>
              <p className="mt-2 text-2xl font-semibold leading-tight text-[var(--text-primary)]">{stat.value}</p>
              {stat.helpText ? <p className="mt-2 text-xs text-[var(--text-secondary)]">{stat.helpText}</p> : null}
            </div>
          ))}
        </div>
      )}
    </PublicOverviewSection>
  );
}
