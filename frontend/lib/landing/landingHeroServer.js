import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";
import { isPublicAnalyticsEligiblePokemonSet } from "@/lib/pokemon/pokemonSetPublicCoverage";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import { selectLandingHeroEntries } from "@/lib/landing/landingHeroSpotlight.mjs";
import { selectExploreRankingRows, selectHeroRankingVisuals, selectMarketContext } from "@/lib/landing/landingPreviews.mjs";
import { resolvePokemonBoosterPackAsset } from "@/lib/pokemon/pokemonBoosterPackAssets.mjs";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";
import { selectLandingDistribution } from "@/lib/landing/landingDistribution.mjs";

const LANDING_TARGETS_LIMIT = 60;
const OPENING_RANKING_LIMIT = 5;
const BACKEND_URL = getBackendApiBaseUrl();

async function getLandingDistribution(setId) {
  const id = String(setId || "").trim();
  if (!id) return null;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 6_000);
  try {
    const response = await fetch(`${BACKEND_URL}/tcgs/pokemon/sets/${encodeURIComponent(id)}/insights/secondary`, {
      cache: "no-store", signal: controller.signal,
    });
    return response.ok ? response.json() : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

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
  const distributionPayload = await getLandingDistribution(openingSpotlightSet?.targetId);
  const openingRankingRows = selectHeroRankingVisuals(
    selectExploreRankingRows(entries, OPENING_RANKING_LIMIT),
    resolvePokemonBoosterPackAsset
  );

  return {
    openingSpotlightSet,
    openingBoosterPackImage: openingRankingRows[0]?.heroVisual?.asset || null,
    openingRankingRows,
    openingDistribution: selectLandingDistribution(distributionPayload, openingSpotlightSet || {}),
    marketContext: selectMarketContext({ entries, meta: payload?.meta || null }),
  };
}
