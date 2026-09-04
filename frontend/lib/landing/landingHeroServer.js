import { getHomepageRankingsSummary } from "@/lib/explore/ripStatisticsServer";
import { isPublicAnalyticsEligiblePokemonSet } from "@/lib/pokemon/pokemonSetPublicCoverage";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import { selectLandingHeroEntries } from "@/lib/landing/landingHeroSpotlight.mjs";
import { selectExploreRankingRows, selectHeroRankingVisuals, selectMarketContext } from "@/lib/landing/landingPreviews.mjs";
import { selectLandingDistribution } from "@/lib/landing/landingDistribution.mjs";
import { resolvePokemonBoosterPackAsset } from "@/lib/pokemon/pokemonBoosterPackAssets.mjs";
import { getPublicBackendRequestHeaders } from "@/lib/authServer";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const OPENING_RANKING_LIMIT = 5;
const BACKEND_URL = getBackendApiBaseUrl();

// Bounded process cache + in-flight join for the spotlight distribution
// read, keyed on the spotlight setId. This is Option (A) from A4: the read
// stays sequential (it needs the spotlight identity first), but repeated
// Homepage requests for the SAME spotlight set within the TTL window never
// re-hit /rip/simulation-evidence. Keying on setId (rather than a single
// fixed key) means a new spotlight set is never hidden behind a stale cache
// entry for the old one, and a genuinely new simulation publication for the
// same set is still picked up within COHORT_TTL_MS.
const DISTRIBUTION_TTL_MS = 120_000;
const distributionCache = new Map(); // setId -> { data, expiresAt }
const distributionInFlight = new Map(); // setId -> Promise

export function __resetLandingDistributionCacheForTests() {
  distributionCache.clear();
  distributionInFlight.clear();
}

/**
 * The #1 set's PUBLIC opening distribution, fetched server-side with the
 * SAME public-only headers as the rankings read (no Cookie/Authorization) —
 * a Plus/Premium session must not change what this returns. Any failure
 * (network error, non-200, malformed body) truthfully returns null so the
 * homepage renders its existing "distribution unavailable" state rather than
 * a fake or interpolated one; the ranking and hero still render regardless.
 */
async function fetchPublicOpeningDistributionUncached(setId) {
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

async function getPublicOpeningDistribution(setId) {
  if (!setId) return null;
  const cached = distributionCache.get(setId);
  if (cached && cached.expiresAt > Date.now()) {
    console.info("[landing-hero-server] distribution_cache_hit", { setId });
    return cached.data;
  }
  const existingInFlight = distributionInFlight.get(setId);
  if (existingInFlight) {
    console.info("[landing-hero-server] distribution_in_flight_join", { setId });
    return existingInFlight;
  }
  const startedAt = Date.now();
  const promise = (async () => {
    try {
      const data = await fetchPublicOpeningDistributionUncached(setId);
      // Only cache a truthfully-successful result; a null (failure/unavailable)
      // read is never cached, so the next request gets a real retry rather than
      // a stale-forever null.
      if (data !== null) {
        distributionCache.set(setId, { data, expiresAt: Date.now() + DISTRIBUTION_TTL_MS });
      }
      console.info("[landing-hero-server] distribution_fetch_complete", {
        setId,
        elapsedMs: Date.now() - startedAt,
        hit: data !== null,
      });
      return data;
    } finally {
      distributionInFlight.delete(setId);
    }
  })();
  distributionInFlight.set(setId, promise);
  return promise;
}

function withRoutes(entry) {
  const target = { target_type: entry.targetType, target_id: entry.targetId, name: entry.name };
  const ripHref = buildTcgSetHrefFromTarget(target, { tab: "overview" });
  return { ...entry, href: ripHref, overviewHref: ripHref, ripScoreHref: ripHref };
}

/**
 * Public landing data is derived from the Homepage's own narrow public
 * Rankings projection (`/explore/rankings/homepage-summary`, Prompt 2 / A2),
 * NOT the general-purpose `/explore/rip-statistics/targets` cohort. That
 * endpoint takes no Authorization/Cookie parameters at all -- every field it
 * returns is intentionally public and identical regardless of the visitor's
 * plan, so this homepage read can never become richer because the visitor
 * happens to have a Plus session cookie. See
 * frontend/lib/explore/ripStatisticsServer.js#getHomepageRankingsSummary for
 * the cache/in-flight-join behavior this relies on.
 */
export async function getLandingPageData() {
  const payload = await getHomepageRankingsSummary().catch(() => null);
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
