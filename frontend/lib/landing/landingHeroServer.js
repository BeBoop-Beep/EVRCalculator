import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";
import { getExploreMarketMovers } from "@/lib/explore/exploreMarketMoversServer";
import { isPublicAnalyticsEligiblePokemonSet } from "@/lib/pokemon/pokemonSetPublicCoverage";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import { selectLandingHeroEntries } from "@/lib/landing/landingHeroSpotlight.mjs";
import {
  rankSetIntelligenceCandidates,
  readDesirability,
  selectOpeningSpotlight,
} from "@/lib/landing/landingSpotlights.mjs";
import { getSetChaseCardsPayload, getSetSealedPayload } from "@/lib/landing/landingSetMedia";
import { selectHeroBoosterPackImage } from "@/lib/landing/landingBoosterPack.mjs";
import {
  selectChaseCards,
  selectExploreRankingRows,
  selectMarketContext,
  selectMarketSignals,
  selectSealedProducts,
  selectSetValueLeaders,
} from "@/lib/landing/landingPreviews.mjs";

// The ranked cohort, both spotlights, the market strip and every ranking come
// out of ONE cached RIP Statistics targets payload — the same contract Explore
// reads. On top of that the page reads Pokemon product content for the two sets
// it features, through the same published set-detail endpoints Overview uses.
// Nothing here is a homepage-only pipeline, nothing re-ranks a cohort in React,
// and every read is independently recoverable: a failure drops its own visual.
const LANDING_TARGETS_LIMIT = 60;

const MARKET_STRIP_LIMIT = 3;
const OPENING_RANKING_LIMIT = 5;
const BEST_SETS_LIMIT = 3;
const SET_VALUE_RANKING_LIMIT = 4;
const HERO_CHASE_CARD_LIMIT = 3;
const FEATURE_CHASE_CARD_LIMIT = 3;
const SEALED_HIGHLIGHT_LIMIT = 2;

/**
 * The large Set Intelligence showcase is built around card art, so a candidate
 * needs at least this many before it can carry the section. A candidate that
 * cannot is passed over for the next one; if none can, the best candidate is
 * still featured and the section falls back to logo-only imagery.
 */
const SHOWCASE_MIN_CHASE_CARDS = 3;

/**
 * How many desirability candidates may be probed for card art before the page
 * settles for the image fallback. Bounded on purpose: this is the only place
 * the homepage can issue a conditional extra request, and in practice the top
 * candidate satisfies it, so the second fetch almost never fires.
 */
const MAX_SHOWCASE_CANDIDATE_PROBES = 2;

/**
 * The set detail Overview destination for a landing entry, plus the RIP Score
 * breakdown deep link behind "Why this set ranks here". Both route through the
 * SAME helper Explore's ladders use, so the homepage can never land on a
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

/**
 * Walk the ordered candidate list until one has enough published chase-card art
 * to carry the showcase. Returns the best candidate either way — the caller
 * renders the documented logo-only fallback when `cards` comes back short.
 */
async function resolveSetIntelligenceShowcase(candidates) {
  const probes = candidates.slice(0, MAX_SHOWCASE_CANDIDATE_PROBES);
  let firstProbed = null;

  for (const candidate of probes) {
    if (!candidate.slug) continue;
    const payload = await getSetChaseCardsPayload(candidate.slug).catch(() => null);
    const cards = selectChaseCards(payload, FEATURE_CHASE_CARD_LIMIT);
    if (firstProbed === null) firstProbed = { set: candidate, cards };
    if (cards.length >= SHOWCASE_MIN_CHASE_CARDS) {
      return { set: candidate, cards };
    }
  }

  // Nothing had full art: keep the best candidate and let its section render
  // with whatever art exists (possibly none) rather than dropping the set.
  return firstProbed || { set: candidates[0] || null, cards: [] };
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

  // ROLE 1 — the published opening rank #1. Not "whatever sorted first".
  const openingSpotlightSet = selectOpeningSpotlight(entries);

  // ROLE 2 — the most desirable eligible set that is NOT the opening spotlight.
  const setIntelligenceCandidates = rankSetIntelligenceCandidates(entries, {
    excludeKey: openingSpotlightSet?.key || null,
  });

  const [openingChaseResult, openingSealedResult, showcaseResult] = await Promise.allSettled([
    openingSpotlightSet?.slug ? getSetChaseCardsPayload(openingSpotlightSet.slug) : Promise.resolve(null),
    openingSpotlightSet?.slug ? getSetSealedPayload(openingSpotlightSet.slug) : Promise.resolve(null),
    resolveSetIntelligenceShowcase(setIntelligenceCandidates),
  ]);

  const openingChasePayload = settled(openingChaseResult);
  const openingSealedPayload = settled(openingSealedResult);
  const showcase = settled(showcaseResult) || { set: null, cards: [] };
  const setIntelligenceSpotlightSet = showcase.set;

  return {
    openingSpotlightSet,
    openingChaseCards: selectChaseCards(openingChasePayload, HERO_CHASE_CARD_LIMIT),
    openingSealedProducts: selectSealedProducts(openingSealedPayload, SEALED_HIGHLIGHT_LIMIT),

    // Decorative hero backdrop only. Resolved from the sealed payload ALREADY
    // fetched above — no extra request — so the pack follows the spotlight set.
    // Null whenever that set publishes no usable product art, in which case the
    // hero renders exactly as it does without this feature.
    openingBoosterPackImage: selectHeroBoosterPackImage(openingSealedPayload, {
      setName: openingSpotlightSet?.name || null,
    }),
    openingCardsAsOf:
      openingChasePayload?.latestMarketDate || openingChasePayload?.latest_market_date || null,

    setIntelligenceSpotlightSet,
    setIntelligenceChaseCards: showcase.cards,
    // Which published field earned this set the slot, for the audit trail. Not
    // rendered as a claim — the section is presented as the Set Intelligence
    // spotlight, never as "the most desirable set".
    setIntelligenceBasis: setIntelligenceSpotlightSet
      ? readDesirability(setIntelligenceSpotlightSet).source
      : null,

    // ROLE 3 — the true published rankings, complete. A set already featured
    // above is NOT removed here; the board must represent the real ranking.
    openingRankingRows: selectExploreRankingRows(entries, OPENING_RANKING_LIMIT),
    bestSetsRows: selectExploreRankingRows(entries, BEST_SETS_LIMIT),
    setValueRankingRows: selectSetValueLeaders(entries, SET_VALUE_RANKING_LIMIT),

    marketSignals: selectMarketSignals({
      entries,
      openingSpotlightSet,
      moversPayload,
    }).slice(0, MARKET_STRIP_LIMIT),
    marketContext: selectMarketContext({ entries, meta: payload?.meta || null }),
  };
}
