import ExploreMarketMovers from "@/components/explore/ExploreMarketMovers";
import ExploreTopRankings from "@/components/explore/ExploreTopRankings";
import PageArtworkAtmosphere from "@/components/ui/PageArtworkAtmosphere";
import { getExploreBackground } from "@/lib/explore/exploreBackgrounds.mjs";
import { getExploreMarketMovers } from "@/lib/explore/exploreMarketMoversServer";
import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";
import { isPublicAnalyticsEligiblePokemonSet } from "@/lib/pokemon/pokemonSetPublicCoverage";
import { projectMarketRankingTargets } from "@/lib/explore/marketRankingsProjection.mjs";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";
import styles from "@/components/explore/explore.module.css";

// Describes only what this page actually renders: the global 7-day card-market
// movers module and the set-value ladder. No forecast, alert or watchlist
// language — none of that exists here.
export const metadata = buildRouteMetadata({
  path: "/Market",
  title: "Pokémon Market Trends & Set Values — inDex",
  description:
    "Pokémon set and card market movement: current set values and the global 7-day card-market movers.",
  ogTitle: "Pokémon Market Trends & Set Values",
});

export default async function MarketPage() {
  const [rankingsResult, moversResult] = await Promise.allSettled([
    getRipStatisticsTargets({ limit: 60 }),
    getExploreMarketMovers(),
  ]);
  const rankingsPayload = rankingsResult.status === "fulfilled" ? rankingsResult.value : null;
  const moversPayload = moversResult.status === "fulfilled"
    ? moversResult.value
    : { marketMovers: { window: "7D", all: [] }, meta: { requestFailed: true } };
  // Eligibility is decided on the COMPLETE target (the coverage predicate reads
  // fields the ladder never renders), and only the survivors are projected — so
  // the client boundary carries the ladder's ~1.2% of each target instead of the
  // whole canonical Rankings document. See marketRankingsProjection.mjs.
  const targets = projectMarketRankingTargets(
    (Array.isArray(rankingsPayload?.targets) ? rankingsPayload.targets : [])
      .filter(isPublicAnalyticsEligiblePokemonSet)
  );
  const loadError = rankingsPayload === null || Boolean(rankingsPayload?.meta?.requestFailed);

  return (
    <div className={`${styles.dashboard} explore-glass-scope relative isolate mx-auto w-full max-w-7xl px-4 pb-20 pt-5 sm:px-6 lg:px-8`}>
      <PageArtworkAtmosphere src={getExploreBackground("pokemon")} dataAttribute="data-market-ambient-artwork" visibilityClassName="hidden desk:block" loading="lazy" />
      <header className="mb-4">
        <h1 className="text-2xl font-semibold text-[var(--text-primary)]">Market</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">What is happening with Pokémon prices?</p>
      </header>
      <div className="space-y-4">
        <ExploreMarketMovers payload={moversPayload} />
        <ExploreTopRankings targets={targets} loadError={loadError} />
      </div>
    </div>
  );
}
