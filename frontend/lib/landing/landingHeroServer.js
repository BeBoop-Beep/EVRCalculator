import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";
import { isPublicAnalyticsEligiblePokemonSet } from "@/lib/pokemon/pokemonSetPublicCoverage";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import { selectLandingHeroEntries } from "@/lib/landing/landingHeroSpotlight.mjs";
import { selectExploreRankingRows, selectHeroRankingVisuals, selectMarketContext } from "@/lib/landing/landingPreviews.mjs";
import { selectLandingDistribution } from "@/lib/landing/landingDistribution.mjs";
import { resolvePokemonBoosterPackAsset } from "@/lib/pokemon/pokemonBoosterPackAssets.mjs";
import { getPublicBackendRequestHeaders } from "@/lib/authServer";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const LANDING_TARGETS_LIMIT = 60;
const OPENING_RANKING_LIMIT = 5;
const BACKEND_URL = getBackendApiBaseUrl();

/**
 * The #1 set's PUBLIC opening distribution, fetched server-side with the
 * SAME public-only headers as the rankings read (no Cookie/Authorization) —
 * a Plus/Premium session must not change what this returns. Any failure
 * (network error, non-200, malformed body) truthfully returns null so the
 * homepage renders its existing "distribution unavailable" state rather than
 * a fake or interpolated one; the ranking and hero still render regardless.
 */
async function getPublicOpeningDistribution(setId) {
  if (!setId) return null;
  try {
    const res = await fetch(`${BACKEND_URL}/tcgs/pokemon/sets/${encodeURIComponent(setId)}/rip/simulation-evidence`, {
      cache: "no-store",
      headers: await getPublicBackendRequestHeaders(),
    });
    if (!res.ok) return null;
    const payload = await res.json().catch(() => null);
    return selectLandingDistribution(payload);
  } catch {
    return null;
  }
}

function withRoutes(entry) {
  const target = { target_type: entry.targetType, target_id: entry.targetId, name: entry.name };
  const ripHref = buildTcgSetHrefFromTarget(target, { tab: "overview" });
  return { ...entry, href: ripHref, overviewHref: ripHref, ripScoreHref: ripHref };
}

/**
 * Public landing data is derived only from the backend's Base projection.
 * `public: true` forces the rankings fetch through getPublicBackendRequestHeaders()
 * (Accept only — no Cookie/Authorization), so this homepage read can never
 * become richer because the visitor happens to have a Plus session cookie.
 */
export async function getLandingPageData() {
  const payload = await getRipStatisticsTargets({ limit: LANDING_TARGETS_LIMIT, public: true }).catch(() => null);
  const targets = Array.isArray(payload?.targets) ? payload.targets : [];
  const entries = selectLandingHeroEntries(
    targets.filter(isPublicAnalyticsEligiblePokemonSet),
  ).map(withRoutes);
  const openingSpotlightSet = entries[0] || null;
  const openingRankingRows = selectHeroRankingVisuals(
    selectExploreRankingRows(entries, OPENING_RANKING_LIMIT),
    resolvePokemonBoosterPackAsset,
  );
  const openingDistribution = await getPublicOpeningDistribution(openingSpotlightSet?.targetId);

  return {
    openingSpotlightSet,
    openingHeroVisual: openingRankingRows[0]?.heroVisual || null,
    openingRankingRows,
    // Public simulation-evidence projection (Base/anonymous-safe fields
    // only) for the #1 set, adapted for RipDistributionChart. Truthfully
    // null when unavailable — never a fabricated/interpolated distribution.
    openingDistribution,
    marketContext: selectMarketContext({ entries, meta: payload?.meta || null }),
  };
}
