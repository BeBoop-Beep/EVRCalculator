import { cache } from "react";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const processCache = new Map();
const TTL = 120_000;
const unavailable = (stale = null) => stale
  ? { ...stale, meta: { ...(stale.meta || {}), stale: true, requestFailed: true } }
  : { sets: [], meta: { requestFailed: true, warnings: ["Global Set Value snapshot unavailable"] } };

export const getExploreSetValueMarket = cache(async function getExploreSetValueMarket() {
  const cached = processCache.get("market");
  if (cached?.expiresAt > Date.now()) return cached.data;
  try {
    const response = await fetch(`${getBackendApiBaseUrl()}/explore/set-value-market`, { cache: "no-store" });
    if (!response.ok) return unavailable(cached?.data);
    const payload = await response.json();
    const data = { sets: Array.isArray(payload?.sets) ? payload.sets : [], meta: payload?.meta || {} };
    processCache.set("market", { data, expiresAt: Date.now() + TTL });
    return data;
  } catch {
    return unavailable(cached?.data);
  }
});
