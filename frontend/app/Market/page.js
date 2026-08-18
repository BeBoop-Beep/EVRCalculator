import ExploreMarketMovers from "@/components/explore/ExploreMarketMovers";
import ExploreTopRankings from "@/components/explore/ExploreTopRankings";
import PokemonMarketOverview from "@/components/explore/PokemonMarketOverview";
import PokemonMarketPerformance from "@/components/explore/PokemonMarketPerformance";
import PageArtworkAtmosphere from "@/components/ui/PageArtworkAtmosphere";
import { getExploreBackground } from "@/lib/explore/exploreBackgrounds.mjs";
import { getExploreMarketMovers } from "@/lib/explore/exploreMarketMoversServer";
import { getExploreSetValueMarket } from "@/lib/explore/exploreSetValueMarketServer";
import { buildCoverageSummary, resolveMarketOverview } from "@/lib/explore/marketOverviewPresentation.mjs";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";
import styles from "@/components/explore/explore.module.css";

// Describes only what this page actually renders: the published Raw Card and
// Top 10 Chase market indexes, the global 7-day card-market movers and the
// set-value ladder. No forecast, capitalization, alert or watchlist language —
// none of that exists here.
export const metadata = buildRouteMetadata({
  path: "/Market",
  title: "Pokémon Market Index, Trends & Set Values — inDex",
  description:
    "Track Pokémon card-market performance, Raw Card and Top Chase indexes, market movers, and current set values.",
  ogTitle: "Pokémon Market Index, Trends & Set Values",
});

export default async function MarketPage() {
  const [setValueResult, moversResult] = await Promise.allSettled([
    getExploreSetValueMarket(),
    getExploreMarketMovers(),
  ]);
  const setValuePayload = setValueResult.status === "fulfilled" ? setValueResult.value : null;
  const moversPayload = moversResult.status === "fulfilled"
    ? moversResult.value
    : { marketMovers: { window: "7D", all: [] }, meta: { requestFailed: true } };
  // Market Overview and the Set Value ladder arrive in the SAME snapshot — the
  // page still makes exactly two backend requests. `marketOverview` is the
  // backend's published authority for every basket value, index value and
  // percentage below; nothing here recomputes one.
  const overview = resolveMarketOverview(setValuePayload);
  // Eligibility is decided on the COMPLETE target (the coverage predicate reads
  // fields the ladder never renders), and only the survivors are projected — so
  // the client boundary carries the ladder's ~1.2% of each target instead of the
  // whole canonical Rankings document. See marketRankingsProjection.mjs.
  const targets = Array.isArray(setValuePayload?.sets) ? setValuePayload.sets : [];
  const loadError = setValuePayload === null || Boolean(setValuePayload?.meta?.requestFailed);
  const coverageSummary = buildCoverageSummary(overview);

  return (
    <div className={`${styles.dashboard} explore-glass-scope relative isolate mx-auto w-full max-w-7xl px-4 pb-20 pt-5 sm:px-6 lg:px-8`}>
      <PageArtworkAtmosphere src={getExploreBackground("pokemon")} dataAttribute="data-market-ambient-artwork" visibilityClassName="hidden desk:block" loading="lazy" />
      <header className="mb-4 flex flex-col gap-2 desk:flex-row desk:items-end desk:justify-between">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold text-[var(--text-primary)]">Pokémon Market</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">Track the value and performance of the Pokémon card market.</p>
        </div>
        {coverageSummary.length ? (
          <p data-market-coverage-summary className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[11px] tabular-nums text-[var(--text-secondary)] desk:justify-end desk:text-right">
            {coverageSummary.map((part, index) => (
              <span key={part} className="whitespace-nowrap">
                {index > 0 ? <span aria-hidden="true" className="mr-1.5 opacity-60">·</span> : null}
                {part}
              </span>
            ))}
          </p>
        ) : null}
      </header>
      <div className="space-y-4">
        <PokemonMarketOverview overview={overview} />
        <PokemonMarketPerformance overview={overview} />
        <ExploreMarketMovers payload={moversPayload} />
        <ExploreTopRankings targets={targets} loadError={loadError} />
      </div>
    </div>
  );
}
