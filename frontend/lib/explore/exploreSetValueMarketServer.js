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

// Test-only: seed the process-local last-known-good cache as an ALREADY WARM
// entry with an arbitrary expiresAt (in the past, to simulate an expired
// freshness window without depending on real elapsed time). This lets tests
// exercise SUCCESS -> (freshness expires) -> FAILURE -> STALE and
// SUCCESS -> FAILURE -> RECOVERY without the 120s TTL actually elapsing.
export function __seedExploreSetValueMarketCacheForTests(data, { expiresAt = Date.now() - 1 } = {}) {
  processCache.set(CACHE_KEY, { data, expiresAt });
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
// Next's `next: { revalidate: 120 }` fetch cache is the single freshness
// authority here — it decides when a response is fresh vs. stale-while-
// revalidating. processCache is NOT a second freshness gate; it exists only
// as (a) an in-process last-known-good fallback for when fetch throws or
// returns non-ok, and (b) a target for inFlight request coalescing. It must
// never skip calling fetch, or it can re-pin a stale response Next already
// served for another full TTL, stacking an extra delay on top of Next's own
// revalidation window before a newly published snapshot is picked up.
async function fetchExploreSetValueMarket() {
  const cached = processCache.get(CACHE_KEY);
  if (inFlight) {
    console.info("[explore-set-value-market] in_flight_join", { key: CACHE_KEY });
    return inFlight;
  }
  const startedAt = Date.now();
  inFlight = (async () => {
    try {
      const response = await fetch(`${getBackendApiBaseUrl()}/explore/set-value-market`, {
        next: { revalidate: 120 },
      });
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
