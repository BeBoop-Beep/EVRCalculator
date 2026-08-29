import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";
import { isPublicAnalyticsEligiblePokemonSet } from "@/lib/pokemon/pokemonSetPublicCoverage";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import { selectLandingHeroEntries } from "@/lib/landing/landingHeroSpotlight.mjs";
import { selectExploreRankingRows, selectHeroRankingVisuals, selectMarketContext } from "@/lib/landing/landingPreviews.mjs";
import { resolvePokemonBoosterPackAsset } from "@/lib/pokemon/pokemonBoosterPackAssets.mjs";

const LANDING_TARGETS_LIMIT = 60;
const OPENING_RANKING_LIMIT = 5;

function withRoutes(entry) {
  const target = { target_type: entry.targetType, target_id: entry.targetId, name: entry.name };
  const ripHref = buildTcgSetHrefFromTarget(target, { tab: "overview" });
  return { ...entry, href: ripHref, overviewHref: ripHref, ripScoreHref: ripHref };
}

/** Public landing data is derived only from the backend's Base projection. */
export async function getLandingPageData() {
  const payload = await getRipStatisticsTargets({ limit: LANDING_TARGETS_LIMIT }).catch(() => null);
  const targets = Array.isArray(payload?.targets) ? payload.targets : [];
  const entries = selectLandingHeroEntries(
    targets.filter(isPublicAnalyticsEligiblePokemonSet),
  ).map(withRoutes);
  const openingSpotlightSet = entries[0] || null;
  const openingRankingRows = selectHeroRankingVisuals(
    selectExploreRankingRows(entries, OPENING_RANKING_LIMIT),
    resolvePokemonBoosterPackAsset,
  );

  return {
    openingSpotlightSet,
    openingBoosterPackImage: openingRankingRows[0]?.heroVisual?.asset || null,
    openingRankingRows,
    // Detailed simulation distribution is Plus-only; never derive it via a
    // paid endpoint on this anonymous/public reader.
    openingDistribution: null,
    marketContext: selectMarketContext({ entries, meta: payload?.meta || null }),
  };
}
