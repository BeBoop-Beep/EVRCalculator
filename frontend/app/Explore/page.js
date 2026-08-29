import { getOpeningEconomics } from "@/lib/explore/openingEconomicsServer";
import { getPokemonSetRouteDirectory } from "@/lib/pokemon/pokemonSetRouteDirectoryServer";
import RankingsLazyClient from "@/components/explore/RankingsLazyClient";
import PageArtworkAtmosphere from "@/components/ui/PageArtworkAtmosphere";
import { getExploreBackground } from "@/lib/explore/exploreBackgrounds.mjs";
import styles from "@/components/explore/explore.module.css";

export default async function ExplorePage() {
  const backgroundUrl = getExploreBackground("pokemon");

  // P0 performance rule: the default Overall lens is powered by the tiny
  // opening-economics publication plus the slim set-route directory. The
  // canonical RIP targets cohort is intentionally absent from this route; it
  // is built only after the user asks for Sets, Eras or Products.
  const [directory, openingEconomics] = await Promise.all([
    getPokemonSetRouteDirectory({ limit: 150 }).catch(() => null),
    getOpeningEconomics(),
  ]);

  const directoryTargets = Array.isArray(directory?.targets) ? directory.targets : [];
  const modeledSetIds = new Set(
    (Array.isArray(openingEconomics?.sets) ? openingEconomics.sets : [])
      .map((entry) => String(entry?.setId || entry?.set_id || "").trim())
      .filter(Boolean),
  );
  // Opening Economics should only decorate identities for sets represented by
  // the published modeled cohort. If that publication is unavailable, retain
  // a bounded directory fallback so Cards filtering/routing still works.
  const targets = modeledSetIds.size
    ? directoryTargets.filter((target) => modeledSetIds.has(String(target?.set_id || target?.target_id || target?.id || "")))
    : directoryTargets.slice(0, 60);
  const rankingsLoadError = directory === null || Boolean(directory?.meta?.requestFailed);
  const rankingsMarketDate = openingEconomics?.marketDate || null;

  return (
    <div data-rankings-wide-shell className={`${styles.dashboard} explore-glass-scope index-environment relative isolate mx-auto w-full max-w-7xl px-4 pb-20 pt-5 md:max-w-[100rem] sm:px-6 lg:px-8`}>
      <PageArtworkAtmosphere
        src={backgroundUrl}
        dataAttribute="data-explore-ambient-artwork"
        visibilityClassName="hidden desk:block"
        loading="lazy"
      />
      <header className="mb-5 w-full">
        <h1 className="text-2xl font-bold tracking-tight text-[var(--text-primary)] sm:text-3xl">Pokémon RIP Rankings</h1>
        <p className="mt-1.5 text-sm text-[var(--text-secondary)]">Current prices, simulated opening outcomes, and collector appeal — compared in one place.</p>
      </header>

      <div data-rankings-data-surface className="w-full">
        <div data-mobile-section>
          <RankingsLazyClient
            targets={targets}
            openingEconomics={openingEconomics}
            rankingsMarketDate={rankingsMarketDate}
            loadError={rankingsLoadError}
          />
        </div>
      </div>
    </div>
  );
}
