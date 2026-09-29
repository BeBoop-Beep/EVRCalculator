async function readJson(response, fallback) {
  const payload = await response.json();
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
