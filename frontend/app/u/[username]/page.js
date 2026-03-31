import PublicFeaturedItemsSection from "@/components/Profile/PublicFeaturedItemsSection";
import PublicPortfolioSnapshot from "@/components/Profile/PublicPortfolioSnapshot";
import PublicPortfolioPerformance from "@/components/Profile/PublicPortfolioPerformance";
import PublicPortfolioHighlights from "@/components/Profile/PublicPortfolioHighlights";
import PublicRecentActivityPreview from "@/components/Profile/PublicRecentActivityPreview";
import { buildPublicOverviewModel } from "@/lib/profile/publicOverviewModel";
import { getCachedPublicRouteContextByUsername } from "@/lib/profile/publicProfileServer";

export default async function PublicProfileOverviewPage({ params }) {
  const { username } = await params;
  const { publicProfile } = await getCachedPublicRouteContextByUsername(username || "");

  const overview = buildPublicOverviewModel({
    publicProfile,
    username: username || "collector",
    enableMockFallback: Boolean(publicProfile),
  });

  return (
    <div className="space-y-6">
      {!publicProfile ? (
        <section className="dashboard-panel rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-5 sm:p-6">
          <p className="text-base font-semibold text-[var(--text-primary)]">Public profile is unavailable</p>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            This collector has not shared enough public data yet. Overview sections remain ready for future data wiring.
          </p>
        </section>
      ) : null}

      <PublicFeaturedItemsSection items={overview.featuredItems} />
      <PublicPortfolioSnapshot stats={overview.snapshotStats} />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <PublicPortfolioPerformance performance={overview.performance} />
        <PublicPortfolioHighlights highlights={overview.highlights} />
      </div>

      <PublicRecentActivityPreview activities={overview.recentActivity} username={username || "collector"} />
    </div>
  );
}
