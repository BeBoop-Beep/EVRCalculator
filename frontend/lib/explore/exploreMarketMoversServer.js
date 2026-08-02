import { cache } from "react";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";
const processCache = new Map();
const TTL = 120_000;
const unavailable = (stale) => stale
  ? { ...stale, meta: { ...(stale.meta || {}), stale: true, requestFailed: true } }
  : { marketMovers: { window: "7D", all: [] }, meta: { requestFailed: true, warnings: ["Global movers unavailable"] } };
export const getExploreMarketMovers = cache(async function getExploreMarketMovers() {
  const cached = processCache.get("7D");
  if (cached?.expiresAt > Date.now()) return cached.data;
  try {
    const response = await fetch(`${getBackendApiBaseUrl()}/explore/card-market-movers`, { cache: "no-store" });
    if (!response.ok) return unavailable(cached?.data);
    const data = await response.json();
    const normalized = { marketMovers: { ...(data?.marketMovers || {}), all: Array.isArray(data?.marketMovers?.all) ? data.marketMovers.all.slice(0, 30) : [] }, meta: data?.meta || {} };
    processCache.set("7D", { data: normalized, expiresAt: Date.now() + TTL });
    return normalized;
  } catch { return unavailable(cached?.data); }
});
