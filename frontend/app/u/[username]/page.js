import PublicFeaturedItemsSection from "@/components/Profile/PublicFeaturedItemsSection";
import PublicRecentActivityPreview from "@/components/Profile/PublicRecentActivityPreview";
import PublicPortfolioOverviewComposer from "@/components/Profile/PublicPortfolioOverviewComposer";
import { mapPublicOverviewToDashboardData } from "@/lib/profile/publicOverviewDashboardAdapter";
import { buildPublicOverviewModel } from "@/lib/profile/publicOverviewModel";
import { getPublicCollectionEntries } from "@/lib/profile/collectionEntryLoader";
import { getCachedPublicRouteContextByUsername } from "@/lib/profile/publicProfileServer";

export default async function PublicProfileOverviewPage({ params }) {
  const { username } = await params;
  const { publicProfile } = await getCachedPublicRouteContextByUsername(username || "");
  const publicCollectionAssets = await getPublicCollectionEntries(username || "");

  const overview = buildPublicOverviewModel({
    publicProfile,
    username: username || "collector",
    collectionAssets: publicCollectionAssets,
    enableMockFallback: Boolean(publicProfile),
  });

  const dashboardData = mapPublicOverviewToDashboardData(overview);

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

      <PublicPortfolioOverviewComposer dashboardData={dashboardData} />

      <PublicFeaturedItemsSection showcase={overview.showcase} username={username || ""} />
      
      <PublicRecentActivityPreview activities={overview.recentActivity} username={username || "collector"} />
    </div>
  );
}
