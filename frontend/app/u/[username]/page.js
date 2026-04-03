import PublicFeaturedItemsSection from "@/components/Profile/PublicFeaturedItemsSection";
import PublicCollectionViewWrapper from "@/components/Profile/PublicCollectionViewWrapper";
import PublicPortfolioOverviewComposer from "@/components/Profile/PublicPortfolioOverviewComposer";
import { mapPublicOverviewToDashboardData } from "@/lib/profile/publicOverviewDashboardAdapter";
import { buildPublicOverviewModel } from "@/lib/profile/publicOverviewModel";
import { buildCollectionStats, getPublicCollectionEntries } from "@/lib/profile/collectionEntryLoader";
import { getCachedPublicProfileByUsername } from "@/lib/profile/publicProfileServer";

export default async function PublicProfileOverviewPage({ params, searchParams }) {
  const { username } = await params;
  await searchParams;

  const publicProfile = await getCachedPublicProfileByUsername(username || "");
  const publicCollectionAssets = await getPublicCollectionEntries(username || "");
  const collectionStats = buildCollectionStats(publicCollectionAssets);
  const canRenderPublicRoot = Boolean(publicProfile);

  const overview = buildPublicOverviewModel({
    publicProfile,
    username: username || "collector",
    collectionAssets: publicCollectionAssets,
    enableMockFallback: canRenderPublicRoot,
  });

  const dashboardData = mapPublicOverviewToDashboardData(overview);

  return (
    <div className="space-y-6">
      {!canRenderPublicRoot ? (
        <section className="dashboard-panel rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-5 sm:p-6">
          <p className="text-base font-semibold text-[var(--text-primary)]">Public profile is unavailable</p>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            This collector has not shared enough public data yet. The public root is reserved for profile-safe collection, showcase, and insight surfaces.
          </p>
        </section>
      ) : (
        <>
          <section>
            <PublicPortfolioOverviewComposer dashboardData={dashboardData} />
          </section>

          <PublicFeaturedItemsSection
            showcase={overview.showcase}
            username={username || ""}
          />

          <PublicCollectionViewWrapper
            items={publicCollectionAssets}
            stats={collectionStats}
            username={username || ""}
            showPerformanceCard={false}
          />
        </>
      )}
    </div>
  );
}
