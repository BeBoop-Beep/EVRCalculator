import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";
import ExploreTableClient from "@/components/explore/ExploreTableClient";
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
    const leftRank = toNumber(left?.overallRipV7?.rank);
    const rightRank = toNumber(right?.overallRipV7?.rank);

    if (leftRank !== null && rightRank !== null && leftRank !== rightRank) {
      return leftRank - rightRank;
    }

    if (leftRank !== null && rightRank === null) {
      return -1;
    }

    if (leftRank === null && rightRank !== null) {
      return 1;
    }

    const leftScore = toNumber(left?.overallRipV7?.relativeScore) ?? -Infinity;
    const rightScore = toNumber(right?.overallRipV7?.relativeScore) ?? -Infinity;
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
  const payload = await getRipStatisticsTargets({ limit: 60 }).catch(() => null);
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

        The sentence below it is the same accessibility affordance, not SEO
        filler: a screen-reader user landing here otherwise gets a heading and
        then a table with no statement of what the page is for. It says only
        what the module beneath it already shows (sets ordered by Overall RIP,
        each linking to its own analysis) and names no weight, coefficient or
        formula.
      */}
      <header className="sr-only">
        <h1>Best Pokémon Sets to Rip Right Now</h1>
        <p>
          Every Pokémon set inDex currently ranks, ordered by Overall RIP. Open a set for its
          Financial RIP, Collector Appeal and modeled opening outcomes.
        </p>
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
      <div className="mx-auto w-full max-w-5xl">
        {/* First ordinary section after the global 7D Movers ticker, so it
            takes the quiet 1px rule rather than the luminous divider. */}
        <div data-mobile-section>
          <ExploreTableClient targets={leaderboardTargets} loadError={rankingsLoadError} />
        </div>
      </div>
    </div>
  );
}
