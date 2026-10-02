const ENDPOINTS = {
  scores: "/api/explore/product-rankings/scores",
  economics: "/api/explore/product-rankings/economics",
};

async function readJson(response) {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(payload?.detail?.message || payload?.message || "Product Rankings request failed");
    error.status = response.status;
    throw error;
  }
  if (payload?.status !== "available" || !Array.isArray(payload?.rows)) throw new Error("Product Rankings are unavailable");
  return payload;
}

export function readProductRankings(view, { fetchImpl = fetch, sessionCache = null, force = false, params = {} } = {}) {
  if (!ENDPOINTS[view]) throw new Error(`Unsupported Product Rankings view: ${view}`);
  const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== ""));
  const url = `${ENDPOINTS[view]}${query.size ? `?${query}` : ""}`;
  const load = () => fetchImpl(url, { credentials: "include", cache: "no-store" }).then(readJson);
  return sessionCache ? sessionCache.request(`products:${view}:${query}`, load, { force }) : load();
}

export function prewarmDefaultProduct({ sessionCache, canViewFullMarket = false } = {}) {
  if (canViewFullMarket) return readProductRankings("scores", {
    sessionCache, params: { page: 1, page_size: 25, sort: "rank", direction: "asc" },
  });
  return import("./rankingsPublicClient.mjs").then(({ readPublicProductCatalogue }) =>
    readPublicProductCatalogue({ sessionCache, params: { page: 1, page_size: 25 } }));
}

export function prewarmDefaultProductEconomics({ sessionCache, canViewFullMarket = false, family = null } = {}) {
  if (!sessionCache || (!canViewFullMarket && !family)) return Promise.resolve(null);
  return readProductRankings("economics", {
    sessionCache,
    params: { page: 1, page_size: 25, ...(family ? { family } : {}), sort: "productName", direction: "asc" },
  }).catch(() => null);
}
