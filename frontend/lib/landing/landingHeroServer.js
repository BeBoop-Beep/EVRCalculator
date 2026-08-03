import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";
import { getExploreMarketMovers } from "@/lib/explore/exploreMarketMoversServer";
import { isPublicAnalyticsEligiblePokemonSet } from "@/lib/pokemon/pokemonSetPublicCoverage";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import { selectLandingHeroEntries } from "@/lib/landing/landingHeroSpotlight.mjs";
import { getSetChaseCardsPayload, getSetSealedPayload } from "@/lib/landing/landingSetMedia";
import {
  selectBestSetsToRip,
  selectChaseCards,
  selectExploreRankingRows,
  selectMarketContext,
  selectMarketSignals,
  selectSealedProducts,
  selectSetValueLeaders,
} from "@/lib/landing/landingPreviews.mjs";

// The ranked cohort, the market strip and every ranking on the page come out of
// ONE cached RIP Statistics targets payload — the same contract Explore reads.
// On top of that the page reads Pokemon product content for the two sets it
// features, through the same published set-detail endpoints the Overview tab
// uses. Nothing here is a homepage-only pipeline, and every one of these reads
// is independently recoverable: a failure drops its own visual, not the page.
const LANDING_TARGETS_LIMIT = 60;

const MARKET_STRIP_LIMIT = 3;
const EXPLORE_PREVIEW_LIMIT = 5;
const BEST_SETS_LIMIT = 3;
const SET_VALUE_LEADER_LIMIT = 4;
const HERO_CHASE_CARD_LIMIT = 3;
const FEATURE_CHASE_CARD_LIMIT = 3;
const SEALED_HIGHLIGHT_LIMIT = 2;

/**
 * The set detail Overview destination for a landing entry, plus the RIP Score
 * breakdown deep link the "How RIP Score works" action uses. Both route through
 * the SAME helper Explore's ladders use, so the homepage can never land on a
 * different tab than the product does for the same set.
 */
function withRoutes(entry) {
  const target = { target_type: entry.targetType, target_id: entry.targetId, name: entry.name };
  return {
    ...entry,
    overviewHref: buildTcgSetHrefFromTarget(target, { tab: "overview" }),
    ripScoreHref: buildTcgSetHrefFromTarget(target, { tab: "insights", section: "rip-score" }),
  };
}

function settled(result) {
  return result.status === "fulfilled" ? result.value : null;
}

export async function getLandingPageData() {
  const [targetsResult, moversResult] = await Promise.allSettled([
    getRipStatisticsTargets({ limit: LANDING_TARGETS_LIMIT }),
    getExploreMarketMovers(),
  ]);

  const payload = settled(targetsResult);
  const moversPayload = settled(moversResult);
  const targets = Array.isArray(payload?.targets) ? payload.targets : [];

  // Same public-analytics gate as Explore: sets whose simulator-era data is not
  // validated for public analytics never reach a public surface, and the
  // landing page is the most public surface there is.
  const eligibleTargets = targets.filter(isPublicAnalyticsEligiblePokemonSet);
  const slugByKey = new Map(
    eligibleTargets.map((target) => [
      `${target?.target_type || "set"}:${target?.target_id || ""}`,
      String(target?.slug || "").trim() || null,
    ])
  );

  const entries = selectLandingHeroEntries(eligibleTargets)
    .map(withRoutes)
    .map((entry) => ({ ...entry, slug: slugByKey.get(entry.key) || null }));

  // The hero features the top-ranked set; the Set Intelligence section features
  // the next one, so the page demonstrates breadth instead of describing one
  // set four times. Both fall back to the hero set when only one is published.
  const heroSet = entries[0] || null;
  const featureSet = entries[1] || heroSet;

  const [heroChaseResult, heroSealedResult, featureChaseResult] = await Promise.allSettled([
    heroSet?.slug ? getSetChaseCardsPayload(heroSet.slug) : Promise.resolve(null),
    heroSet?.slug ? getSetSealedPayload(heroSet.slug) : Promise.resolve(null),
    featureSet?.slug && featureSet.key !== heroSet?.key
      ? getSetChaseCardsPayload(featureSet.slug)
      : Promise.resolve(null),
  ]);

  const heroChasePayload = settled(heroChaseResult);
  const heroChaseCards = selectChaseCards(heroChasePayload, HERO_CHASE_CARD_LIMIT);
  const featureChasePayload = settled(featureChaseResult) || heroChasePayload;

  return {
    heroSet,
    featureSet,
    heroChaseCards,
    heroSealedProducts: selectSealedProducts(settled(heroSealedResult), SEALED_HIGHLIGHT_LIMIT),
    heroCardsAsOf:
      heroChasePayload?.latestMarketDate || heroChasePayload?.latest_market_date || null,
    featureChaseCards: selectChaseCards(featureChasePayload, FEATURE_CHASE_CARD_LIMIT),
    marketSignals: selectMarketSignals({ entries, moversPayload }).slice(0, MARKET_STRIP_LIMIT),
    exploreRows: selectExploreRankingRows(entries, EXPLORE_PREVIEW_LIMIT),
    bestSets: selectBestSetsToRip(entries, BEST_SETS_LIMIT),
    setValueLeaders: selectSetValueLeaders(entries, SET_VALUE_LEADER_LIMIT),
    marketContext: selectMarketContext({ entries, meta: payload?.meta || null }),
  };
}
