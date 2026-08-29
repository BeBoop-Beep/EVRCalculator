import { cache } from "react";
import { cookies } from "next/headers";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const processCache = new Map();
const TTL = 120_000;
// The snapshot publishes THREE top-level keys: marketOverview (the global Raw /
// Top 10 Chase / Sealed index families), sets (the Set Value ladder) and meta. The
// reconstruction below must carry all three — an earlier version rebuilt only
// { sets, meta } and silently dropped the published Market Overview, so the
// page had no way to render it without inventing the numbers itself.
const unavailable = (stale = null) => stale
  ? { ...stale, marketOverview: stale.marketOverview ?? null, meta: { ...(stale.meta || {}), stale: true, requestFailed: true } }
  : { marketOverview: null, sets: [], meta: { requestFailed: true, warnings: ["Global Set Value snapshot unavailable"] } };

export const getExploreSetValueMarket = cache(async function getExploreSetValueMarket() {
  try {
    const cookieHeader = (await cookies()).toString();
    const preparedResponse = await fetch(`${getBackendApiBaseUrl()}/market/explorer/snapshot`, {
      cache: "no-store",
      headers: cookieHeader ? { Cookie: cookieHeader } : {},
    });
    // The backend has independently authenticated and authorized this exact
    // request. Never process-cache this paid payload across users.
    const response = preparedResponse.ok
      ? preparedResponse
      : await fetch(`${getBackendApiBaseUrl()}/explore/set-value-market`, { cache: "no-store" });
    const cached = processCache.get("public-market");
    if (!response.ok) return unavailable(cached?.data);
    const payload = await response.json();
    const data = {
      marketOverview: payload?.marketOverview && typeof payload.marketOverview === "object" ? payload.marketOverview : null,
      sets: Array.isArray(payload?.sets) ? payload.sets : [],
      initialSelectedSetMovers:
        payload?.initialSelectedSetMovers && typeof payload.initialSelectedSetMovers === "object"
          ? payload.initialSelectedSetMovers
          : null,
      meta: payload?.meta || {},
    };
    if (!preparedResponse.ok) {
      processCache.set("public-market", { data, expiresAt: Date.now() + TTL });
    }
    return data;
  } catch {
    return unavailable(cached?.data);
  }
});
