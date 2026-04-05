import SectionEmptyState from "@/components/Profile/SectionEmptyState";

const COLLECTION_INSIGHTS = [
  {
    id: "ci-1",
    title: "Top 3 assets represent 39% of portfolio value",
    detail: "Concentration rose 2.1 points this week. Consider rotating gains into broader set exposure.",
    tone: "watch",
  },
  {
    id: "ci-2",
    title: "Sealed allocation increased this week",
    detail: "Sealed products moved from 21% to 24% of value as recent boxes appreciated.",
    tone: "positive",
  },
  {
    id: "ci-3",
    title: "Charizard ex SIR gained 8.7% over 7 days",
    detail: "This is currently your strongest single-asset weekly move by dollar contribution.",
    tone: "positive",
  },
  {
    id: "ci-4",
    title: "7 wishlist items are now below target price",
    detail: "Best opportunities are clustered in SV-era illustration rares with tighter spreads.",
    tone: "positive",
  },
  {
    id: "ci-5",
    title: "Vintage cards outperformed modern cards this month",
    detail: "Vintage segment returned +5.2% vs +1.4% for modern, led by low-pop holo staples.",
    tone: "watch",
  },
];

function toneClass(tone) {
  if (tone === "positive") return "text-emerald-300";
  if (tone === "watch") return "text-amber-300";
  return "text-[var(--text-secondary)]";
}

export default function MyCollectionOperationalIntelligence() {
  return (
    <section className="dashboard-panel rounded-2xl border border-[var(--border-subtle)] p-4 sm:p-5">
      <div className="mb-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">Collection Insights</p>
        <p className="mt-1 text-xs text-[var(--text-secondary)] sm:text-sm">
          Actionable owner-focused signals for concentration, momentum, and acquisition opportunities.
        </p>
      </div>

      <section>
        {COLLECTION_INSIGHTS.length === 0 ? (
          <SectionEmptyState
            title="No collection insights yet"
            description="Insight items will appear as your collection activity and pricing history grow."
            icon="📊"
          />
        ) : (
          <ul className="space-y-2.5">
            {COLLECTION_INSIGHTS.map((insight) => (
              <li key={insight.id} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium text-[var(--text-primary)]">{insight.title}</p>
                  <span className={`text-xs font-semibold ${toneClass(insight.tone)}`}>
                    {insight.tone === "positive" ? "Actionable" : "Watch"}
                  </span>
                </div>
                <p className="mt-1 text-xs text-[var(--text-secondary)]">{insight.detail}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </section>
  );
}
