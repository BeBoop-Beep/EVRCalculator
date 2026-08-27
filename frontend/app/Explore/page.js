import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";
import { getOverallProductRankings } from "@/lib/explore/overallProductRankingsServer";
import { getOpeningEconomics } from "@/lib/explore/openingEconomicsServer";
import ProductFamilyRankingsClient from "@/components/explore/ProductFamilyRankingsClient";
import PageArtworkAtmosphere from "@/components/ui/PageArtworkAtmosphere";
import { getExploreBackground } from "@/lib/explore/exploreBackgrounds.mjs";
import { isPublicAnalyticsEligiblePokemonSet } from "@/lib/pokemon/pokemonSetPublicCoverage";
import { projectRankingsTargets } from "@/lib/explore/rankingsClientProjection.mjs";
import styles from "@/components/explore/explore.module.css";

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Server-side ordering of the leaderboard, by the CANONICAL Overall RIP V7
 * rank.
 *
 * This used to sort by `pack_rank` and `relative_pack_score` — the retired
 * 45/25/20/10 blend the payload's own `meta.deprecatedFields` marks "Do not
 * read". `ExploreTableClient` re-sorts by the selected mode so the legacy order
 * was usually overwritten, but every other consumer of `leaderboardTargets`
 * (the Top Rankings ladder, the "N ranked sets" count) inherited it, and a
 * hidden legacy ordering is one refactor away from being a visible one.
 *
 * A target with no canonical rank sorts last rather than borrowing a legacy
 * number.
 */
function rankTargets(targets) {
  return [...targets].sort((left, right) => {
    const leftRank = toNumber(left?.setRipV1?.rank);
    const rightRank = toNumber(right?.setRipV1?.rank);

    if (leftRank !== null && rightRank !== null && leftRank !== rightRank) {
      return leftRank - rightRank;
    }

    if (leftRank !== null && rightRank === null) {
      return -1;
    }

    if (leftRank === null && rightRank !== null) {
      return 1;
    }

    const leftScore = toNumber(left?.setRipV1?.score) ?? -Infinity;
    const rightScore = toNumber(right?.setRipV1?.score) ?? -Infinity;
    if (leftScore !== rightScore) {
      return rightScore - leftScore;
    }

    return String(left?.name || "").localeCompare(String(right?.name || ""));
  });
}

// Title, description, canonical URL and og:url for this page live in
// app/Rankings/page.js. /Rankings is its canonical address and /Explore
// permanently redirects there (see next.config.mjs), so declaring metadata here
// would put a live route's canonical identity in a directory that no longer
// answers requests.

export default async function ExplorePage({ searchParams }) {
  const resolvedSearchParams = (await searchParams) || {};
  const backgroundUrl = getExploreBackground("pokemon");
  // Fetched in parallel with the rankings targets, not after them: the Overall
  // lens is the default view, so a serial fetch would put its latency directly
  // in front of first paint. `getOpeningEconomics` never rejects — it resolves
  // to an explicit unavailable contract — so it cannot fail the whole page.
  const [payload, initialOverallProductRankings, openingEconomics] = await Promise.all([
    getRipStatisticsTargets({ limit: 60 }).catch(() => null),
    getOverallProductRankings("full_market"),
    getOpeningEconomics(),
  ]);
  const targets = Array.isArray(payload?.targets) ? payload.targets : [];
  // Sword & Shield's simulator-era data is not yet validated for public
  // analytics (incomplete pull/hit-rate model, unblended subsets) — see
  // pokemonSetPublicCoverage.js. Filtering here means every consumer below
  // (the ranked table, its "N ranked sets" count, the Top Rankings ladder)
  // only ever sees eligible sets; this never touches how any score is computed.
  const eligibleTargets = targets.filter(isPublicAnalyticsEligiblePokemonSet);
  const sortedTargets = rankTargets(eligibleTargets);
  // Eligibility and the canonical rank sort BOTH run on the complete targets
  // above — this projects only what crosses into ExploreTableClient ("use
  // client"), which otherwise serializes every canonical block into the RSC
  // flight payload and ships it to the browser. Measured on the current cohort:
  // 1,118,440 -> 41,141 bytes (-96.3%) with zero behavioural difference across
  // all eight ranking modes, all seven sortable columns in both directions,
  // Collector Appeal, 1D movement and routing. See rankingsClientProjection.mjs
  // — it does NOT narrow the backend fetch, which stays the shared canonical
  // cohort read.
  const leaderboardTargets = projectRankingsTargets(sortedTargets);
  // requestFailed marks a genuine fetch/backend failure (see
  // ripStatisticsServer.js's withTargetsRequestFailureMeta) as distinct from
  // a real "no ranked sets yet" empty result — payload === null covers the
  // unexpected-throw case the .catch above guards against.
  const rankingsLoadError = payload === null || Boolean(payload?.meta?.requestFailed);

  return (
    // The root layout already provides the <main> landmark, so this is a plain
    // container — two <main> elements would announce two main regions.
    <div data-rankings-wide-shell className={`${styles.dashboard} explore-glass-scope index-environment relative isolate mx-auto w-full max-w-7xl px-4 pb-20 pt-5 md:max-w-[100rem] sm:px-6 lg:px-8`}>
      <PageArtworkAtmosphere
        src={backgroundUrl}
        dataAttribute="data-explore-ambient-artwork"
        visibilityClassName="hidden desk:block"
        loading="lazy"
      />
      {/*
        No outer context box: the modules sit directly on the application
        canvas. The visible heading answers the page question immediately; the
        one-line context names inputs without putting methodology before data.
      */}
      <header className="mb-5 w-full">
        <h1 className="text-2xl font-bold tracking-tight text-[var(--text-primary)] sm:text-3xl">Pokémon RIP Rankings</h1>
        <p className="mt-1.5 text-sm text-[var(--text-secondary)]">Current prices, simulated opening outcomes, and collector appeal — compared in one place.</p>
      </header>

      {/*
        Primary dashboard row. Both modules are siblings of one grid, top
        aligned, and each renders independently — a failure in one leaves the
        other intact because they share only the already-fetched target list.
      */}
      {/* Mobile owns this boundary through the section variant below; a bottom
          margin here would stack on top of it. Declared desktop-first — the
          original mb-5 is the unconditional base and mobile subtracts it — so
          the desktop value can never lose a source-order coin toss to the
          mobile override the way `mb-0 desk:mb-5` did. */}
      <div data-rankings-data-surface className="w-full">
        {/* First ordinary section after the global 7D Movers ticker, so it
            takes the quiet 1px rule rather than the luminous divider. */}
        <div data-mobile-section>
          <ProductFamilyRankingsClient targets={leaderboardTargets} productFamilyRankings={payload?.productFamilyRankings} initialOverallProductRankings={initialOverallProductRankings} openingEconomics={openingEconomics} eraSetStrength={payload?.eraSetStrengthV1} loadError={rankingsLoadError} />
        </div>
      </div>
    </div>
  );
}
