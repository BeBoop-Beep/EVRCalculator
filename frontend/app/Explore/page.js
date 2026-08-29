import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";
import { getOpeningEconomics } from "@/lib/explore/openingEconomicsServer";
import RankingsLazyClient from "@/components/explore/RankingsLazyClient";
import PageArtworkAtmosphere from "@/components/ui/PageArtworkAtmosphere";
import { getExploreBackground } from "@/lib/explore/exploreBackgrounds.mjs";
import { isPublicAnalyticsEligiblePokemonSet } from "@/lib/pokemon/pokemonSetPublicCoverage";
import { projectRankingsTargets } from "@/lib/explore/rankingsClientProjection.mjs";
import styles from "@/components/explore/explore.module.css";

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function rankTargets(targets) {
  return [...targets].sort((left, right) => {
    const leftRank = toNumber(left?.setRipV1?.rank);
    const rightRank = toNumber(right?.setRipV1?.rank);

    if (leftRank !== null && rightRank !== null && leftRank !== rightRank) return leftRank - rightRank;
    if (leftRank !== null && rightRank === null) return -1;
    if (leftRank === null && rightRank !== null) return 1;

    const leftScore = toNumber(left?.setRipV1?.score) ?? -Infinity;
    const rightScore = toNumber(right?.setRipV1?.score) ?? -Infinity;
    if (leftScore !== rightScore) return rightScore - leftScore;

    return String(left?.name || "").localeCompare(String(right?.name || ""));
  });
}

export default async function ExplorePage() {
  const backgroundUrl = getExploreBackground("pokemon");

  // P0 performance rule: the default Overall lens must not pay for Product or
  // Era ranking payloads it does not render. Those contracts now load only
  // when their lens is selected through /api/explore/rankings/lens.
  const [payload, openingEconomics] = await Promise.all([
    getRipStatisticsTargets({ limit: 60 }).catch(() => null),
    getOpeningEconomics(),
  ]);

  const targets = Array.isArray(payload?.targets) ? payload.targets : [];
  const eligibleTargets = targets.filter(isPublicAnalyticsEligiblePokemonSet);
  const leaderboardTargets = projectRankingsTargets(rankTargets(eligibleTargets));
  const rankingsLoadError = payload === null || Boolean(payload?.meta?.requestFailed);
  const rankingsMarketDate = payload?.meta?.comparisonSnapshots?.currentMarketDate || null;

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
            targets={leaderboardTargets}
            openingEconomics={openingEconomics}
            rankingsMarketDate={rankingsMarketDate}
            loadError={rankingsLoadError}
          />
        </div>
      </div>
    </div>
  );
}
