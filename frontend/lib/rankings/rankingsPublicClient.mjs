async function readJson(url, fetchImpl) {
  const response = await fetchImpl(url, { credentials: "include", cache: "no-store" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.detail?.message || payload?.message || "Public Rankings request failed");
  return payload;
}

export function readPublicRankingsHeadlines(entityType, { fetchImpl = fetch, sessionCache = null, force = false } = {}) {
  if (!new Set(["set", "era"]).has(entityType)) throw new Error("entityType must be set or era");
  const load = () => readJson(`/api/tcgs/pokemon/rankings/headlines?entity_type=${entityType}`, fetchImpl);
  return sessionCache ? sessionCache.request(`public:headlines:${entityType}`, load, { force }) : load();
}

export function readPublicPackEconomicsPreview({ fetchImpl = fetch, sessionCache = null, force = false } = {}) {
  const load = () => readJson("/api/tcgs/pokemon/rankings/pack-economics-preview", fetchImpl);
  return sessionCache ? sessionCache.request("public:pack-economics-preview", load, { force }) : load();
}

export function readPublicProductCatalogue({ fetchImpl = fetch, sessionCache = null, force = false, params = {} } = {}) {
  const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== ""));
  const url = `/api/tcgs/pokemon/rankings/product-catalogue${query.size ? `?${query}` : ""}`;
  const load = () => readJson(url, fetchImpl);
  return sessionCache ? sessionCache.request(`public:product-catalogue:${query}`, load, { force }) : load();
}
