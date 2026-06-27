const SET_PAGE_QUERY_ROOT = "pokemon-set-page";

function normalizeSetId(setId) {
  return String(setId || "").trim() || null;
}

export const pokemonSetPageQueryKeys = {
  shell: (setId) => [SET_PAGE_QUERY_ROOT, "shell", normalizeSetId(setId)],
  setValueTrend: (setId, options = {}) => [
    SET_PAGE_QUERY_ROOT,
    "set-value-trend",
    normalizeSetId(setId),
    String(options.scope || "all"),
    Number(options.days || 365),
  ],
  cards: (setId) => [SET_PAGE_QUERY_ROOT, "cards", normalizeSetId(setId)],
  marketDashboard: (setId, options = {}) => [
    SET_PAGE_QUERY_ROOT,
    "market-dashboard",
    normalizeSetId(setId),
    String(options.window || "365d").toLowerCase(),
  ],
  validation: (setId, options = {}) => [
    SET_PAGE_QUERY_ROOT,
    "validation",
    normalizeSetId(setId),
    String(options.kind || "all"),
  ],
};

export function queryKeyToString(queryKey) {
  return (Array.isArray(queryKey) ? queryKey : [queryKey])
    .map((part) => (part === null || part === undefined ? "" : String(part)))
    .join(":");
}
