import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";
import { isPublicAnalyticsEligiblePokemonSet } from "@/lib/pokemon/pokemonSetPublicCoverage";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import { selectLandingHeroEntries } from "@/lib/landing/landingHeroSpotlight.mjs";
import { selectExploreRankingRows, selectMarketContext } from "@/lib/landing/landingPreviews.mjs";
import { resolvePokemonBoosterPackAsset } from "@/lib/pokemon/pokemonBoosterPackAssets.mjs";

const LANDING_TARGETS_LIMIT = 60;
const OPENING_RANKING_LIMIT = 5;

function withRoutes(entry) {
  const target = { target_type: entry.targetType, target_id: entry.targetId, name: entry.name };
  return {
    ...entry,
    overviewHref: buildTcgSetHrefFromTarget(target, { tab: "overview" }),
    ripScoreHref: buildTcgSetHrefFromTarget(target, { tab: "insights", section: "rip-score" }),
  };
}

/** One published Explore payload powers the hero, board, and evidence section. */
export async function getLandingPageData() {
  const payload = await getRipStatisticsTargets({ limit: LANDING_TARGETS_LIMIT }).catch(() => null);
  const targets = Array.isArray(payload?.targets) ? payload.targets : [];
  const eligibleTargets = targets.filter(isPublicAnalyticsEligiblePokemonSet);
  const entries = selectLandingHeroEntries(eligibleTargets).map(withRoutes);
  const openingSpotlightSet = entries[0] || null;

  return {
    openingSpotlightSet,
    openingBoosterPackImage: resolvePokemonBoosterPackAsset(openingSpotlightSet?.canonicalKey),
    openingRankingRows: selectExploreRankingRows(entries, OPENING_RANKING_LIMIT),
    marketContext: selectMarketContext({ entries, meta: payload?.meta || null }),
  };
}
