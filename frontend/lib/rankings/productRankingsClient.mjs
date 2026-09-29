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

export function readProductRankings(view, { fetchImpl = fetch, sessionCache = null, force = false } = {}) {
  if (!ENDPOINTS[view]) throw new Error(`Unsupported Product Rankings view: ${view}`);
  const load = () => fetchImpl(ENDPOINTS[view], { credentials: "include", cache: "no-store" }).then(readJson);
  return sessionCache ? sessionCache.request(`products:${view}`, load, { force }) : load();
}
