import { cache } from "react";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const CACHE_KEY = "public-market";
const processCache = new Map();
let inFlight = null;
const TTL = 120_000;

// Test-only: force a deterministic cold cache for cache-behavior tests.
export function __resetExploreSetValueMarketCacheForTests() {
  processCache.clear();
  inFlight = null;
}
// The snapshot publishes THREE top-level keys: marketOverview (the global Raw /
// Top 10 Chase / Sealed index families), sets (the Set Value ladder) and meta. The
// reconstruction below must carry all three — an earlier version rebuilt only
// { sets, meta } and silently dropped the published Market Overview, so the
// page had no way to render it without inventing the numbers itself.
export const unavailableExploreSetValueMarket = (stale = null) => stale
  ? { ...stale, marketOverview: stale.marketOverview ?? null, meta: { ...(stale.meta || {}), stale: true, requestFailed: true } }
  : { marketOverview: null, sets: [], meta: { requestFailed: true, warnings: ["Global Set Value snapshot unavailable"] } };

export function normalizeExploreSetValueMarket(payload) {
  return {
    marketOverview: payload?.marketOverview && typeof payload.marketOverview === "object" ? payload.marketOverview : null,
    sets: Array.isArray(payload?.sets) ? payload.sets : [],
    initialSelectedSetMovers:
      payload?.initialSelectedSetMovers && typeof payload.initialSelectedSetMovers === "object"
        ? payload.initialSelectedSetMovers
        : null,
    meta: payload?.meta || {},
  };
}

// Public Set Value Market data is a single intentional public contract:
// `/explore/set-value-market` is the compact, prepared, unauthenticated
// snapshot that already carries marketOverview + sets + initialSelectedSetMovers.
// It must NEVER probe the paid `/market/explorer/snapshot` endpoint first —
// that endpoint requires auth/entitlement and anonymous/Base viewers would
// otherwise pay for a failed auth round-trip (and Plus/Premium viewers would
// otherwise be handed the full multi-MB paid publication) just to render the
// public Market page. Paid Explorer data, when actually needed by the paid
// Explorer UI, is loaded through its own intentional path elsewhere.
async function fetchExploreSetValueMarket() {
  const cached = processCache.get(CACHE_KEY);
  if (cached?.expiresAt > Date.now()) {
    console.info("[explore-set-value-market] cache_hit", { key: CACHE_KEY });
    return cached.data;
  }
  if (inFlight) {
    console.info("[explore-set-value-market] in_flight_join", { key: CACHE_KEY });
    return inFlight;
  }
  const startedAt = Date.now();
  inFlight = (async () => {
    try {
      const response = await fetch(`${getBackendApiBaseUrl()}/explore/set-value-market`, { cache: "no-store" });
      if (!response.ok) {
        console.warn("[explore-set-value-market] backend_error", { status: response.status });
        return unavailableExploreSetValueMarket(cached?.data);
      }
      const payload = await response.json();
      const data = normalizeExploreSetValueMarket(payload);
      processCache.set(CACHE_KEY, { data, expiresAt: Date.now() + TTL });
      console.info("[explore-set-value-market] fresh_response", { elapsedMs: Date.now() - startedAt });
      return data;
    } catch (error) {
      console.warn("[explore-set-value-market] request_failed", { error: error?.message || String(error) });
      return unavailableExploreSetValueMarket(cached?.data);
    } finally {
      inFlight = null;
    }
  })();
  return inFlight;
}

export const getExploreSetValueMarket = cache(fetchExploreSetValueMarket);
