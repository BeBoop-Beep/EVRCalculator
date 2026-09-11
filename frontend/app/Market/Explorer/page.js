import MarketExplorerAccessGate from "@/components/explore/MarketExplorerAccessGate";
import MarketExplorerClient from "@/components/explore/MarketExplorerClient";
import PageArtworkAtmosphere from "@/components/ui/PageArtworkAtmosphere";
import { getExploreBackground } from "@/lib/explore/exploreBackgrounds.mjs";
import { getAuthenticatedUserFromCookiesWithTimeout } from "@/lib/authServer";
import { resolveMarketExplorerPlanAccess } from "@/lib/access/indexPlanAccess.mjs";
import { getExploreSetValueMarket } from "@/lib/explore/exploreSetValueMarketServer";
import { getMarketExplorerPreparedDirectory } from "@/lib/explore/marketExplorerPreparedServer";
import { resolveInitialExplorerState } from "@/lib/explore/marketExplorerState.mjs";
import {
  resolveCardSegmentReconciliation,
  resolveCardSegmentSeries,
  resolveSealedSegmentReconciliation,
  resolveSealedSegmentSeries,
  resolveTopChaseSegmentStatus,
} from "@/lib/explore/marketExplorerSeries.mjs";
import { buildCoverageSummary, resolveMarketOverview } from "@/lib/explore/marketOverviewPresentation.mjs";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";
import styles from "@/components/explore/explore.module.css";

// Market Explorer — the deep-dive research destination.
//
// /Market stays the broad public market pulse and is untouched. This page
// answers the next question: WHICH part of the market is driving that
// performance. Phase 1 does that with the only market series that exist
// canonically today — the three published global families.
//
// DATA. Exactly ONE backend request, the same global Set Value Market snapshot
// /Market already reads, because that payload already carries all three
// families. No new endpoint, no new query, and nothing recomputed here.
export const metadata = buildRouteMetadata({
  path: "/Market/Explorer",
  title: "Market Explorer — Compare Pokémon Market Segments | inDex",
  description:
    "Compare Raw Card, Top 10 Chase and Sealed market performance — plus Booster Box, ETB, Pokémon Center ETB, Booster Bundle and Pack submarkets — side by side.",
  ogTitle: "Market Explorer — Compare Pokémon Market Segments",
});

export default async function MarketExplorerPage({ searchParams }) {
  const [resolvedSearchParams, payload, auth, preparedDirectory] = await Promise.all([
    Promise.resolve(searchParams).catch(() => null),
    getExploreSetValueMarket().catch(() => null),
    // PLAN, NOT LOGIN, decides what this workspace offers. Resolved here so the
    // first paint is already correct; a failure or timeout yields no user,
    // which is basic access — the gate fails CLOSED.
    getAuthenticatedUserFromCookiesWithTimeout().catch(() => ({ user: null })),
    getMarketExplorerPreparedDirectory(),
  ]);
  const user = auth?.user || null;
  const planAccess = resolveMarketExplorerPlanAccess(user);
  const overview = resolveMarketOverview(payload);
  // Sealed product-family submarkets ride in the SAME snapshot — still exactly
  // one backend request. A snapshot published before the segmentation simply
  // carries none, and the Sealed Product Family axis reports unavailable.
  const sealedSegments = resolveSealedSegmentSeries(payload);
  const reconciliation = resolveSealedSegmentReconciliation(payload);
  // Card-rarity submarkets ride in the SAME snapshot too — still exactly one
  // backend request for the whole workspace.
  const cardSegments = resolveCardSegmentSeries(payload);
  const cardReconciliation = resolveCardSegmentReconciliation(payload);
  const topChaseSegmentStatus = resolveTopChaseSegmentStatus(payload);
  // ONE parser owns the URL contract; no component reads searchParams itself.
  const initialState = resolveInitialExplorerState(
    overview, resolvedSearchParams, sealedSegments, cardSegments
  );
  const coverageSummary = buildCoverageSummary(overview);

  return (
    // WIDER THAN THE REST OF THE APP, DELIBERATELY AND ONLY HERE.
    // max-w-7xl (80rem) is the shell every ordinary dashboard page uses; this
    // is a research terminal whose central object is a comparison chart, and at
    // 1728px that shell left roughly 500px of unused viewport on either side.
    // 118rem is close to full width with real gutters, and the class is on THIS
    // page's wrapper — /Market and every other route are untouched.
    <div className={`${styles.dashboard} explore-glass-scope index-environment relative isolate mx-auto w-full max-w-[118rem] px-4 pb-20 pt-3 desk:px-6 desk:pt-5 sm:px-6 lg:px-8 2xl:px-10`}>
      <PageArtworkAtmosphere src={getExploreBackground("pokemon")} dataAttribute="data-market-ambient-artwork" visibilityClassName="hidden desk:block" loading="lazy" />

      {/* The entitlement boundary. Market Explorer ITSELF is open to everyone —
          the Asset Market layer is the public market pulse, and hiding the
          whole workspace would remove the thing the /Market CTA points at.
          What varies by plan is DEPTH, and that is decided inside the
          workspace from `user`. */}
      <MarketExplorerAccessGate planAccess={planAccess}>
        <MarketExplorerClient
          overview={overview}
          sealedSegments={sealedSegments}
          cardSegments={cardSegments}
          reconciliation={reconciliation}
          cardReconciliation={cardReconciliation}
          topChaseSegmentStatus={topChaseSegmentStatus}
          initialState={initialState}
          user={user}
          coverageSummary={coverageSummary}
          preparedDirectory={preparedDirectory}
        />
      </MarketExplorerAccessGate>
    </div>
  );
}
