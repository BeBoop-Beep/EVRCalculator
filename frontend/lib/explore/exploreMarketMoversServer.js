import { cache } from "react";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";
const CACHE_KEY = "7D";
const processCache = new Map();
let inFlight = null;
const TTL = 120_000;
const unavailable = (stale) => stale
  ? { ...stale, meta: { ...(stale.meta || {}), stale: true, requestFailed: true } }
  : { marketMovers: { window: "7D", all: [] }, meta: { requestFailed: true, warnings: ["Global movers unavailable"] } };

// Test-only: force a deterministic cold cache for cache-behavior tests.
export function __resetExploreMarketMoversCacheForTests() {
  processCache.clear();
}

// Test-only: seed the process-local last-known-good cache with an arbitrary
// expiresAt (in the past by default) to simulate an expired freshness window
// without waiting out the real 120s TTL.
export function __seedExploreMarketMoversCacheForTests(data, { expiresAt = Date.now() - 1 } = {}) {
  processCache.set(CACHE_KEY, { data, expiresAt });
}

// Next's `next: { revalidate: 120 }` fetch cache is the single freshness
// authority here. processCache is only an in-process last-known-good
// fallback for thrown/non-ok fetches plus an inFlight coalescing target —
// it must never gate/skip the fetch call itself, or it can re-pin a stale
// response Next already served for another full TTL on top of Next's own
// revalidation window.
export const getExploreMarketMovers = cache(async function getExploreMarketMovers() {
  const cached = processCache.get(CACHE_KEY);
  if (inFlight) return inFlight;
  inFlight = (async () => {
    try {
      const response = await fetch(`${getBackendApiBaseUrl()}/explore/card-market-movers`, {
        next: { revalidate: 120 },
      });
      if (!response.ok) return unavailable(cached?.data);
      const data = await response.json();
      const normalized = { marketMovers: { ...(data?.marketMovers || {}), all: Array.isArray(data?.marketMovers?.all) ? data.marketMovers.all.slice(0, 30) : [] }, meta: data?.meta || {} };
      processCache.set(CACHE_KEY, { data: normalized, expiresAt: Date.now() + TTL });
      return normalized;
    } catch {
      return unavailable(cached?.data);
    } finally {
      inFlight = null;
    }
  })();
  return inFlight;
});
