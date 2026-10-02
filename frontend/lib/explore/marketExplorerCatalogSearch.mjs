import { boundedFetch, EXPLORER_REQUEST_BOUNDS_MS } from "./marketExplorerBoundedRequest.mjs";

// Market Explorer contextual catalog search. Prepared markets are grouped
// before their physical instruments.
export const SEARCH_ENDPOINT = "/api/market/explorer/catalog-search";
export const SEARCH_MIN_LENGTH = 2;
export const SEARCH_LIMIT = 12;
export const SEARCH_DEBOUNCE_MS = 250;
export const SEARCH_PLACEHOLDER = Object.freeze({ cards: "Search cards…", sealed: "Search sealed products…", graded: "Search graded cards…" });

const usable = (value) => (typeof value === "string" && value.trim() ? value.trim() : null);
export function leafContext(result) {
  const parts = result?.asset === "sealed"
    ? [result?.setName, result?.variantLabel || result?.productType || result?.productFamily]
    : [result?.setName, result?.variantLabel || result?.rarity];
  return parts.filter(usable).join(" · ");
}
export function resolveSearchResultAction(result) {
  if (!result) return { primary: { kind: "none" } };
  if (result.asset === "graded" || String(result.availability || "").toUpperCase() === "INSUFFICIENT_AUTHORITY") {
    return { primary: { kind: "unavailable", reason: usable(result.reason) || "Graded leaf search is not available yet." } };
  }
  if (usable(result.marketKey)) return { primary: { kind: "market", marketKey: result.marketKey } };
  if (!usable(result.instrumentId)) return { primary: { kind: "none" } };
  const item = result.asset === "sealed"
    ? { asset: "sealed", instrumentId: result.instrumentId, name: result.displayName, setName: result.setName, productFamily: result.productFamily, productType: result.productType, variantLabel: result.variantLabel, imageUrl: result.imageUrl }
    : { asset: "cards", instrumentId: result.instrumentId, name: result.displayName, setName: result.setName, cardNumber: result.cardNumber, rarity: result.rarity, edition: result.edition, printingType: result.printingType, specialType: result.specialType, variantLabel: result.variantLabel, imageUrl: result.imageUrl };
  return { primary: { kind: "direct", item } };
}
export async function fetchCatalogSearch({ asset, q, limit = SEARCH_LIMIT, signal }) {
  const query = new URLSearchParams({ asset, q, limit: String(limit) });
  const response = await boundedFetch(`${SEARCH_ENDPOINT}?${query}`, { credentials: "include", cache: "no-store" },
    { signal, timeoutMs: EXPLORER_REQUEST_BOUNDS_MS.search,
      timeoutCode: "CATALOG_SEARCH_TIMEOUT", timeoutMessage: "Search took too long. Please try again." });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error("Search is temporarily unavailable");
    error.status = response.status; error.code = payload?.code || "CATALOG_SEARCH_FAILED"; throw error;
  }
  const rows = Array.isArray(payload?.results) ? payload.results : [];
  return rows.map((row) => ({
    ...row,
    resultKind: row.result_kind,
    displayName: row.market_key && !/\s[—-]\s(?:Cards|Sealed|Graded)$/i.test(String(row.label || ""))
      ? `${row.label} — ${asset === "sealed" ? "Sealed" : asset === "graded" ? "Graded" : "Cards"}`
      : row.label,
    marketKey: row.market_key,
    instrumentId: row.instrument_id,
    setId: row.set_id,
    imageUrl: row.image_url,
    setName: row.subtitle,
    ...(row.metadata || {}),
  })).sort((left, right) => {
    const group = (row) => row.marketKey ? 0 : 1;
    return group(left) - group(right) || Number(right.relevance || 0) - Number(left.relevance || 0);
  });
}
const isAbort = (error) => error?.name === "AbortError";
export function createCatalogSearchController({ fetchResults = fetchCatalogSearch, debounceMs = SEARCH_DEBOUNCE_MS, limit = SEARCH_LIMIT, minLength = SEARCH_MIN_LENGTH, setTimer = (fn, ms) => setTimeout(fn, ms), clearTimer = (id) => clearTimeout(id) } = {}) {
  let state = { status: "idle", query: "", asset: "cards", results: [], error: null };
  let token = 0; let timer = null; let controller = null; const listeners = new Set();
  const emit = (patch) => { state = { ...state, ...patch }; for (const listener of [...listeners]) listener(); };
  const cancelInflight = () => { if (timer != null) { clearTimer(timer); timer = null; } if (controller) { controller.abort(); controller = null; } };
  function run(query, asset) {
    const mine = ++token; cancelInflight(); const needle = String(query || "").trim();
    if (needle.length < minLength) { emit({ status: "idle", query: needle, asset, results: [], error: null }); return; }
    emit({ status: "loading", query: needle, asset, error: null });
    timer = setTimer(async () => {
      timer = null; controller = new AbortController(); const mineController = controller;
      try {
        const results = await fetchResults({ asset, q: needle, limit, signal: mineController.signal });
        if (mine !== token) return;
        controller = null; emit({ status: "ready", results: (Array.isArray(results) ? results : []).slice(0, limit), error: null });
      } catch (error) {
        if (mine !== token || isAbort(error)) return;
        controller = null; emit({ status: "error", results: [], error: { code: error?.code || "CATALOG_SEARCH_FAILED", status: error?.status || 0 } });
      }
    }, debounceMs);
  }
  return { subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); }, getSnapshot: () => state,
    search: (query, asset = state.asset) => run(query, asset), retry: () => run(state.query, state.asset),
    clear() { token += 1; cancelInflight(); emit({ status: "idle", query: "", results: [], error: null }); },
    dispose() { token += 1; cancelInflight(); listeners.clear(); } };
}
