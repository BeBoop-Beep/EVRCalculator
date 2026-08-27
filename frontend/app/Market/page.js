import ExploreMarketMovers from "@/components/explore/ExploreMarketMovers";
import PokemonMarketAnalysis from "@/components/explore/PokemonMarketAnalysis";
import SetMarketExplorer from "@/components/explore/SetMarketExplorer";
import PageArtworkAtmosphere from "@/components/ui/PageArtworkAtmosphere";
import { getExploreBackground } from "@/lib/explore/exploreBackgrounds.mjs";
import { getExploreMarketMovers } from "@/lib/explore/exploreMarketMoversServer";
import { getExploreSetValueMarket } from "@/lib/explore/exploreSetValueMarketServer";
import { buildCoverageSummary, projectMarketPageOverview, resolveMarketOverview } from "@/lib/explore/marketOverviewPresentation.mjs";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";
import styles from "@/components/explore/explore.module.css";

// Describes only what this page actually renders: the published Raw Card,
// Top 10 Chase and Sealed market indexes, the global 7-day card-market movers and the
// Set Market explorer. No forecast, capitalization, alert or watchlist
// language — none of that exists here.
export const metadata = buildRouteMetadata({
  path: "/Market",
  title: "Pokémon Market Index, Trends & Set Values — inDex",
  description:
    "Track Pokémon Raw Card, Top Chase, and Sealed market performance, market movers, and current set values.",
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
  const marketPageOverview = projectMarketPageOverview(overview);
  // The Set Market explorer reads these targets directly; the snapshot is
  // already the compact Market-domain publication (setId, name, era, logo,
  // currentSetValue, windows, trend), not the canonical Rankings document.
  const targets = Array.isArray(setValuePayload?.sets) ? setValuePayload.sets : [];
  const initialSelectedSetMovers = setValuePayload?.initialSelectedSetMovers || null;
  const loadError = setValuePayload === null || Boolean(setValuePayload?.meta?.requestFailed);
  const coverageSummary = buildCoverageSummary(overview);

  return (
    <div className={`${styles.dashboard} explore-glass-scope index-environment relative isolate mx-auto w-full max-w-7xl px-4 pb-20 pt-3 desk:pt-5 sm:px-6 lg:px-8`}>
      <PageArtworkAtmosphere src={getExploreBackground("pokemon")} dataAttribute="data-market-ambient-artwork" visibilityClassName="hidden desk:block" loading="lazy" />
      <header className="mb-3 flex flex-col gap-1 desk:mb-4 desk:gap-2 desk:flex-row desk:items-end desk:justify-between">
        <div className="min-w-0">
          <h1 className="text-[20px] font-semibold text-[var(--text-primary)] desk:text-2xl">Pokémon Market</h1>
          <p className="mt-1 hidden text-sm text-[var(--text-secondary)] desk:block">Track the value and performance of the Pokémon card market.</p>
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
      {/* Locked hierarchy: header metadata -> the EXISTING 7D Market Movers,
          unchanged and merely moved -> the unified Market Overview + Market
          Performance surface -> the unified Set Market master-detail surface. */}
      <div className="desk:space-y-4">
        <div className="max-desk:-mx-4 max-desk:px-4 sm:max-desk:-mx-6 sm:max-desk:px-6"><ExploreMarketMovers payload={moversPayload} /></div>
        <div data-mobile-section className="max-desk:-mx-4 sm:max-desk:-mx-6"><PokemonMarketAnalysis overview={marketPageOverview} /></div>
        <div data-mobile-section className="max-desk:-mx-4 sm:max-desk:-mx-6"><SetMarketExplorer targets={targets} initialSelectedSetMovers={initialSelectedSetMovers} loadError={loadError} /></div>
      </div>
    </div>
  );
}
