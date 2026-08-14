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

// The spotlight set's simulation distribution was the ONLY landing data source
// with no cross-request cache: targets and the global movers each hold a 120s
// process cache, while this ~240 ms request ran on every single homepage render
// — ~86% of warm homepage server time once the corrected Rankings publication
// brought the targets leg down.
//
// The TTL is 120s and the key is the set id, matching `ripStatisticsServer` and
// `exploreMarketMoversServer` exactly. That is deliberate: this payload is
// published by the SAME daily set-insights publication those two read, so a
// third, shorter freshness boundary would not buy fresher data — it would only
// make the three sources on one page disagree about how old "now" is. Freshness
// semantics are unchanged; only the number of identical requests is.
const DISTRIBUTION_TTL_MS = 120_000;
const distributionCache = new Map();

async function getLandingDistribution(setId) {
  const id = String(setId || "").trim();
  if (!id) return null;

  const cached = distributionCache.get(id);
  if (cached && cached.expiresAt > Date.now()) return cached.data;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 6_000);
  try {
    const response = await fetch(`${BACKEND_URL}/tcgs/pokemon/sets/${encodeURIComponent(id)}/insights/secondary`, {
      cache: "no-store", signal: controller.signal,
    });
    if (!response.ok) return null;
    const data = await response.json();
    // Only a successful payload is cached. A failed request must retry on the
    // next render rather than pinning the homepage to a null distribution — the
    // section renders unavailable, and 120s of that would be a visible outage.
    distributionCache.set(id, { data, expiresAt: Date.now() + DISTRIBUTION_TTL_MS });
    return data;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

function withRoutes(entry) {
  const target = { target_type: entry.targetType, target_id: entry.targetId, name: entry.name };
  const ripHref = buildTcgSetHrefFromTarget(target, { tab: "overview" });
  return {
    ...entry,
    href: ripHref,
    overviewHref: ripHref,
    ripScoreHref: ripHref,
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
