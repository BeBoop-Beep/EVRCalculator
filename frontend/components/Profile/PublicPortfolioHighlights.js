import PublicOverviewSection from "@/components/Profile/PublicOverviewSection";

export default function PublicPortfolioHighlights({ highlights = [] }) {
  return (
    <PublicOverviewSection title="Portfolio Highlights" subtitle="Quick standout moments from this collection.">
      {highlights.length === 0 ? (
        <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)] p-8 text-sm text-[var(--text-secondary)]">
          Portfolio highlights are not available yet.
        </div>
      ) : (
        <div className="space-y-3">
          {highlights.map((item) => (
            <div
              key={item.id}
              className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] px-4 py-3"
            >
              <div className="flex items-center justify-between gap-4">
                <p className="text-sm text-[var(--text-secondary)]">{item.label}</p>
                <p className="text-sm font-semibold text-[var(--text-primary)]">{item.value}</p>
              </div>
              {item.context ? <p className="mt-1 text-xs text-[var(--text-secondary)]">{item.context}</p> : null}
            </div>
          ))}
        </div>
      )}
    </PublicOverviewSection>
  );
}
