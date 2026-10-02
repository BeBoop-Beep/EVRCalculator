import { boundedFetch, EXPLORER_REQUEST_BOUNDS_MS } from "./marketExplorerBoundedRequest.mjs";

export const SEARCH_ENDPOINT = "/api/market/explorer/catalog-search";
export const SEARCH_MIN_LENGTH = 2;
export const SEARCH_LIMIT = 12;
export const SEARCH_DEBOUNCE_MS = 250;
export const SEARCH_PLACEHOLDER = Object.freeze({ cards: "Search cards…", sealed: "Search sealed products…", graded: "Search graded cards…" });

const usable = (value) => (typeof value === "string" && value.trim() ? value.trim() : null);
export function leafContext(result) {
  const parts = result?.asset === "sealed" ? [result?.setName, result?.variantLabel || result?.productType || result?.productFamily] : [result?.setName, result?.variantLabel || result?.rarity];
  return parts.filter(usable).join(" · ");
}
export function resolveSearchResultAction(result) {
  if (!result) return { primary: { kind: "none" } };
  if (result.asset === "graded" || String(result.availability || "").toUpperCase() === "INSUFFICIENT_AUTHORITY") return { primary: { kind: "unavailable", reason: usable(result.reason) || "Graded leaf search is not available yet." } };
  if (usable(result.marketKey)) return { primary: { kind: "market", marketKey: result.marketKey } };
  if (!usable(result.instrumentId)) return { primary: { kind: "none" } };
  const item = result.asset === "sealed"
    ? { asset: "sealed", instrumentId: result.instrumentId, name: result.displayName, setName: result.setName, productFamily: result.productFamily, productType: result.productType, variantLabel: result.variantLabel, imageUrl: result.imageUrl }
    : { asset: "cards", instrumentId: result.instrumentId, name: result.displayName, setName: result.setName, cardNumber: result.cardNumber, rarity: result.rarity, edition: result.edition, printingType: result.printingType, specialType: result.specialType, variantLabel: result.variantLabel, imageUrl: result.imageUrl };
  return { primary: { kind: "direct", item } };
}
function normalizeRow(row, asset) {
  return { ...row, resultKind: row.result_kind,
    displayName: row.market_key && !/\s[—-]\s(?:Cards|Sealed|Graded)$/i.test(String(row.label || "")) ? `${row.label} — ${asset === "sealed" ? "Sealed" : asset === "graded" ? "Graded" : "Cards"}` : row.label,
    marketKey: row.market_key, instrumentId: row.instrument_id, setId: row.set_id, imageUrl: row.image_url,
    setName: row.subtitle, ...(row.metadata || {}) };
}
export async function fetchCatalogSearch({ asset, q, limit = SEARCH_LIMIT, cursor = null, signal }) {
  const query = new URLSearchParams({ asset, q, limit: String(limit) });
  if (cursor != null) query.set("after", String(cursor));
  const response = await boundedFetch(`${SEARCH_ENDPOINT}?${query}`, { credentials: "include", cache: "no-store" }, { signal, timeoutMs: EXPLORER_REQUEST_BOUNDS_MS.search, timeoutCode: "CATALOG_SEARCH_TIMEOUT", timeoutMessage: "Search took too long. Please try again." });
  const payload = await response.json().catch(() => null);
  if (!response.ok) { const error = new Error("Search is temporarily unavailable"); error.status = response.status; error.code = payload?.code || "CATALOG_SEARCH_FAILED"; throw error; }
  const rows = Array.isArray(payload?.results) ? payload.results : [];
  return { results: rows.map((row) => normalizeRow(row, asset)), nextCursor: payload?.nextCursor ?? null, context: payload?.context === "set" ? "set" : "name", generationId: payload?.generationId || null };
}
const isAbort = (error) => error?.name === "AbortError";
export function createCatalogSearchController({ fetchResults = fetchCatalogSearch, debounceMs = SEARCH_DEBOUNCE_MS, limit = SEARCH_LIMIT, minLength = SEARCH_MIN_LENGTH, setTimer = (fn, ms) => setTimeout(fn, ms), clearTimer = (id) => clearTimeout(id) } = {}) {
  let state = { status: "idle", query: "", asset: "cards", results: [], error: null, nextCursor: null, loadingMore: false };
  let token = 0; let timer = null; let controller = null; const listeners = new Set();
  const emit = (patch) => { state = { ...state, ...patch }; for (const listener of [...listeners]) listener(); };
  const cancelInflight = () => { if (timer != null) { clearTimer(timer); timer = null; } if (controller) { controller.abort(); controller = null; } };
  function run(query, asset) {
    const mine = ++token; cancelInflight(); const needle = String(query || "").trim();
    if (needle.length < minLength) { emit({ status: "idle", query: needle, asset, results: [], error: null, nextCursor: null, loadingMore: false }); return; }
    emit({ status: "loading", query: needle, asset, results: [], error: null, nextCursor: null, loadingMore: false });
    timer = setTimer(async () => {
      timer = null; controller = new AbortController(); const mineController = controller;
      try {
        const page = await fetchResults({ asset, q: needle, limit, cursor: null, signal: mineController.signal });
        if (mine !== token) return;
        const normalized = Array.isArray(page) ? { results: page, nextCursor: null } : page;
        controller = null; emit({ status: "ready", results: normalized?.results || [], nextCursor: normalized?.nextCursor ?? null, error: null });
      } catch (error) {
        if (mine !== token || isAbort(error)) return;
        controller = null; emit({ status: "error", results: [], nextCursor: null, error: { code: error?.code || "CATALOG_SEARCH_FAILED", status: error?.status || 0 } });
      }
    }, debounceMs);
  }
  async function loadMore() {
    if (state.status !== "ready" || state.loadingMore || state.nextCursor == null) return;
    const mine = token; const cursor = state.nextCursor; controller = new AbortController(); const mineController = controller; emit({ loadingMore: true, error: null });
    try {
      const page = await fetchResults({ asset: state.asset, q: state.query, limit, cursor, signal: mineController.signal });
      if (mine !== token) return;
      const normalized = Array.isArray(page) ? { results: page, nextCursor: null } : page;
      const seen = new Set(state.results.map((row) => row.instrumentId || row.marketKey));
      const additions = (normalized?.results || []).filter((row) => !seen.has(row.instrumentId || row.marketKey));
      controller = null; emit({ results: [...state.results, ...additions], nextCursor: normalized?.nextCursor ?? null, loadingMore: false });
    } catch (error) {
      if (mine !== token || isAbort(error)) return;
      controller = null; emit({ loadingMore: false, error: { code: error?.code || "CATALOG_SEARCH_FAILED", status: error?.status || 0 } });
    }
  }
  return { subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); }, getSnapshot: () => state, search: (query, asset = state.asset) => run(query, asset), retry: () => run(state.query, state.asset), loadMore,
    clear() { token += 1; cancelInflight(); emit({ status: "idle", query: "", results: [], error: null, nextCursor: null, loadingMore: false }); }, dispose() { token += 1; cancelInflight(); listeners.clear(); } };
}
