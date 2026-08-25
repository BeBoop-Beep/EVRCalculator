import MarketExplorerAccessGate from "@/components/explore/MarketExplorerAccessGate";
import MarketExplorerClient from "@/components/explore/MarketExplorerClient";
import PageArtworkAtmosphere from "@/components/ui/PageArtworkAtmosphere";
import { getExploreBackground } from "@/lib/explore/exploreBackgrounds.mjs";
import { getExploreSetValueMarket } from "@/lib/explore/exploreSetValueMarketServer";
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
  const [resolvedSearchParams, payload] = await Promise.all([
    Promise.resolve(searchParams).catch(() => null),
    getExploreSetValueMarket().catch(() => null),
  ]);
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
    <div className={`${styles.dashboard} explore-glass-scope index-environment relative isolate mx-auto w-full max-w-7xl px-4 pb-20 pt-3 desk:pt-5 sm:px-6 lg:px-8`}>
      <PageArtworkAtmosphere src={getExploreBackground("pokemon")} dataAttribute="data-market-ambient-artwork" visibilityClassName="hidden desk:block" loading="lazy" />

      {/* Compact research header. Deliberately not a hero — this is a workspace. */}
      <header className="mb-3 flex flex-col gap-1 desk:mb-4 desk:gap-2 desk:flex-row desk:items-end desk:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-[20px] font-semibold text-[var(--text-primary)] desk:text-2xl">Market Explorer</h1>
            <span data-market-explorer-plan-badge className="inline-flex flex-none items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)]/45 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
              Index Plus
            </span>
          </div>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">Compare performance across Pokémon market segments.</p>
        </div>
        {coverageSummary.length ? (
          <p data-market-coverage-summary className="flex flex-wrap items-center gap-x-1 gap-y-0 text-[10px] leading-tight tabular-nums text-[var(--text-secondary)] desk:justify-end desk:gap-x-1.5 desk:text-right desk:text-[11px]">
            {coverageSummary.map((part, index) => (
              <span key={part} className="whitespace-nowrap">
                {index > 0 ? <span aria-hidden="true" className="mr-1.5 opacity-60">·</span> : null}
                {part}
              </span>
            ))}
          </p>
        ) : null}
      </header>

      {/* The entitlement boundary. Open in this branch — no gate exists yet —
          but the workspace is already wrapped, so installing the real one is a
          change inside MarketExplorerAccessGate and nowhere else. */}
      <MarketExplorerAccessGate>
        <MarketExplorerClient
          overview={overview}
          sealedSegments={sealedSegments}
          cardSegments={cardSegments}
          reconciliation={reconciliation}
          cardReconciliation={cardReconciliation}
          topChaseSegmentStatus={topChaseSegmentStatus}
          initialState={initialState}
        />
      </MarketExplorerAccessGate>
    </div>
  );
}
