import { canonicalCardQueryKey } from "./rankingsSessionCache.mjs";

export async function readJson(response, fallback) {
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error("Card Rankings backend returned an invalid response.");
  }
  if (!response.ok) {
    throw new Error(payload?.detail?.message || payload?.message || fallback);
  }
  return payload;
}

export function fetchCardRankingFacets(lens) {
  return fetch(`/api/explore/card-ranking-facets?lens=${encodeURIComponent(lens)}`, {
    cache: "no-store",
  }).then((response) => readJson(response, "Unable to load card filters"));
}

export function buildCardRowsParams({ lens, page, filters }) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: "50",
    sort: filters.sort,
    direction: filters.direction,
  });
  if (lens) params.set("lens", lens);
  for (const key of ["search", "era", "set", "rarity", "min_price", "max_price"]) {
    const value = String(filters[key] || "").trim();
    if (value) params.set(key, value);
  }
  return params;
}

export function fetchCollectorRows(params) {
  return fetch(`/api/explore/card-collector-appeal?${params}`, { cache: "no-store" })
    .then((response) => readJson(response, "Unable to load Collector Appeal"));
}

export function fetchChaseRows(params) {
  return fetch(`/api/explore/card-chase-efficiency?${params}`, { cache: "no-store" })
    .then((response) => readJson(response, "Unable to load Chase Efficiency"));
}

export const DEFAULT_COLLECTOR_FILTERS = Object.freeze({ search: "", era: "", set: "", rarity: "", sort: "rank", direction: "asc" });

export function defaultCollectorRequest() {
  const params = buildCardRowsParams({ lens: "overall", page: 1, filters: DEFAULT_COLLECTOR_FILTERS });
  return { params, rowKey: canonicalCardQueryKey(params, "collector:overall"), facetKey: "cards:facets:collector" };
}

export function prewarmDefaultCollector({ sessionCache, entitled, authStatus, saveData = false } = {}) {
  if (!sessionCache || !entitled || saveData || !(authStatus === "resolved" || authStatus === "degraded")) return Promise.resolve(null);
  const { params, rowKey, facetKey } = defaultCollectorRequest();
  return Promise.all([
    sessionCache.request(facetKey, () => fetchCardRankingFacets("collector")),
    sessionCache.request(rowKey, () => fetchCollectorRows(params)),
  ]).catch(() => null);
}

export function prewarmDefaultChase({ sessionCache, entitled, authStatus, saveData = false } = {}) {
  if (!sessionCache || !entitled || saveData || !(authStatus === "resolved" || authStatus === "degraded")) return Promise.resolve(null);
  const filters = { ...DEFAULT_COLLECTOR_FILTERS, min_price: "", max_price: "" };
  const params = buildCardRowsParams({ page: 1, filters });
  return Promise.all([
    sessionCache.request("cards:facets:chase", () => fetchCardRankingFacets("chase")),
    sessionCache.request(canonicalCardQueryKey(params), () => fetchChaseRows(params)),
  ]).catch(() => null);
}
