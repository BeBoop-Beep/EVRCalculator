import { cache } from "react";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const processCache = new Map();
const TTL = 120_000;
// The snapshot publishes THREE top-level keys: marketOverview (the global Raw /
// Top 10 Chase index families), sets (the Set Value ladder) and meta. The
// reconstruction below must carry all three — an earlier version rebuilt only
// { sets, meta } and silently dropped the published Market Overview, so the
// page had no way to render it without inventing the numbers itself.
const unavailable = (stale = null) => stale
  ? { ...stale, marketOverview: stale.marketOverview ?? null, meta: { ...(stale.meta || {}), stale: true, requestFailed: true } }
  : { marketOverview: null, sets: [], meta: { requestFailed: true, warnings: ["Global Set Value snapshot unavailable"] } };

export const getExploreSetValueMarket = cache(async function getExploreSetValueMarket() {
  const cached = processCache.get("market");
  if (cached?.expiresAt > Date.now()) return cached.data;
  try {
    const response = await fetch(`${getBackendApiBaseUrl()}/explore/set-value-market`, { cache: "no-store" });
    if (!response.ok) return unavailable(cached?.data);
    const payload = await response.json();
    const data = {
      marketOverview: payload?.marketOverview && typeof payload.marketOverview === "object" ? payload.marketOverview : null,
      sets: Array.isArray(payload?.sets) ? payload.sets : [],
      meta: payload?.meta || {},
    };
    processCache.set("market", { data, expiresAt: Date.now() + TTL });
    return data;
  } catch {
    return unavailable(cached?.data);
  }
});
