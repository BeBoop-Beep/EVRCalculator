import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";
import ExploreTableClient from "@/components/explore/ExploreTableClient";
import ExploreTopRankings from "@/components/explore/ExploreTopRankings";
import ExploreMarketMovers from "@/components/explore/ExploreMarketMovers";
import PageArtworkAtmosphere from "@/components/ui/PageArtworkAtmosphere";
import { getExploreMarketMovers } from "@/lib/explore/exploreMarketMoversServer";
import { getExploreBackground } from "@/lib/explore/exploreBackgrounds.mjs";
import { isPublicAnalyticsEligiblePokemonSet } from "@/lib/pokemon/pokemonSetPublicCoverage";
import styles from "@/components/explore/explore.module.css";

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function rankTargets(targets) {
  return [...targets].sort((left, right) => {
    const leftRank = toNumber(left?.pack_rank);
    const rightRank = toNumber(right?.pack_rank);

    if (leftRank !== null && rightRank !== null && leftRank !== rightRank) {
      return leftRank - rightRank;
    }

    if (leftRank !== null && rightRank === null) {
      return -1;
    }

    if (leftRank === null && rightRank !== null) {
      return 1;
    }

    const leftScore = toNumber(left?.relative_pack_score) ?? -Infinity;
    const rightScore = toNumber(right?.relative_pack_score) ?? -Infinity;
    if (leftScore !== rightScore) {
      return rightScore - leftScore;
    }

    return String(left?.name || "").localeCompare(String(right?.name || ""));
  });
}

export const metadata = {
  title: "Explore — inDex",
  description:
    "Ranked set intelligence: the strongest sets to rip right now, Overall and Financial RIP scores, tiers, and opening economics.",
};

export default async function ExplorePage({ searchParams }) {
  const resolvedSearchParams = (await searchParams) || {};
  const backgroundUrl = getExploreBackground("pokemon");
  const [rankingsResult, moversResult] = await Promise.allSettled([
    getRipStatisticsTargets({ limit: 60 }),
    getExploreMarketMovers(),
  ]);
  const payload = rankingsResult.status === "fulfilled" ? rankingsResult.value : null;
  const moversPayload = moversResult.status === "fulfilled"
    ? moversResult.value
    : { marketMovers: { window: "7D", all: [] }, meta: { requestFailed: true } };
  const targets = Array.isArray(payload?.targets) ? payload.targets : [];
  // Sword & Shield's simulator-era data is not yet validated for public
  // analytics (incomplete pull/hit-rate model, unblended subsets) — see
  // pokemonSetPublicCoverage.js. Filtering here means every consumer below
  // (the ranked table, its "N ranked sets" count, the Top Rankings ladder)
  // only ever sees eligible sets; this never touches how pack_score/relative
  // scores are computed.
  const eligibleTargets = targets.filter(isPublicAnalyticsEligiblePokemonSet);
  const sortedTargets = rankTargets(eligibleTargets);
  const leaderboardTargets = sortedTargets;
  // requestFailed marks a genuine fetch/backend failure (see
  // ripStatisticsServer.js's withTargetsRequestFailureMeta) as distinct from
  // a real "no ranked sets yet" empty result — payload === null covers the
  // unexpected-throw case the .catch above guards against.
  const rankingsLoadError = payload === null || Boolean(payload?.meta?.requestFailed);

  return (
    // The root layout already provides the <main> landmark, so this is a plain
    // container — two <main> elements would announce two main regions.
    <div className={`${styles.dashboard} explore-glass-scope relative isolate mx-auto w-full max-w-7xl px-4 pb-20 pt-5 sm:px-6 lg:px-8`}>
      <PageArtworkAtmosphere
        src={backgroundUrl}
        dataAttribute="data-explore-ambient-artwork"
        visibilityClassName="hidden desk:block"
        loading="lazy"
      />
      {/*
        No outer context box: the modules sit directly on the application
        canvas. The page heading stays in the document for structure but is
        visually hidden — the first thing on screen is the ranked data.
      */}
      <h1 className="sr-only">Explore</h1>

      {/*
        Primary dashboard row. Both modules are siblings of one grid, top
        aligned, and each renders independently — a failure in one leaves the
        other intact because they share only the already-fetched target list.
      */}
      {/* Mobile owns this boundary through the section variant below; a bottom
          margin here would stack on top of it. Desktop keeps its original
          grid spacing. */}
      <div className="mb-0 desk:mb-5">
        <ExploreMarketMovers payload={moversPayload} />
      </div>
      <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[minmax(19rem,1fr)_minmax(0,2fr)]">
        {/* First ordinary section after the global 7D Movers ticker, so it
            takes the quiet 1px rule rather than the luminous divider. */}
        <div data-mobile-section data-mobile-section-variant="after-movers">
          <ExploreTopRankings targets={leaderboardTargets} loadError={rankingsLoadError} />
        </div>
        <div data-mobile-section>
          <ExploreTableClient targets={leaderboardTargets} loadError={rankingsLoadError} />
        </div>
      </div>
    </div>
  );
}
