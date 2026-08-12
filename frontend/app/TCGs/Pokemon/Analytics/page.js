import SecondaryNav from "@/components/SecondaryNav";
import { NOINDEX_FOLLOW_ROBOTS } from "@/lib/seo/routeMetadata.mjs";

// "Analytics dashboard coming soon" — a placeholder with no content. There is
// no single true replacement URL to redirect it to (the analytics it describes
// are spread across /Rankings, /Market and the per-set pages), so per the
// legacy-route policy it is excluded from the index rather than redirected or
// deleted.
//
// `'use client'` was removed so this route can declare metadata: the component
// uses no state, effects or handlers.
export const metadata = { robots: NOINDEX_FOLLOW_ROBOTS };

export default function AnalyticsPage() {
  return (
    <div className="min-h-screen bg-[var(--app-background)]">
      <SecondaryNav basePath="/TCGs/Pokemon" />
      <main className="w-full px-2 md:px-6 lg:px-10 py-8">
        <div className="max-w-6xl mx-auto">
          <div className="dashboard-container">
          <h1 className="text-3xl md:text-4xl font-bold text-[var(--text-primary)] mb-4">
            Pokémon TCG Analytics
          </h1>
          <p className="text-lg text-[var(--text-secondary)] mb-8">
            Analyze market trends and collection insights.
          </p>

          <div className="bg-[var(--surface-panel)] rounded-lg border border-[var(--border-subtle)] p-8">
            <div className="text-center text-[var(--text-secondary)]">
              <p className="mb-4">Analytics dashboard coming soon...</p>
              <p className="text-sm">This page will display detailed analytics, trends, and market insights for Pokémon TCG cards.</p>
            </div>
          </div>
            </div>
          </div>
      </main>
    </div>
  );
}
