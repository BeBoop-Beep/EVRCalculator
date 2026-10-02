import { boundedFetch, EXPLORER_REQUEST_BOUNDS_MS } from "./marketExplorerBoundedRequest.mjs";

// Market Explorer contextual search is intentionally COMPOSITE: prepared market
// matches first, then physical instruments. A set-name query such as
// "Prismatic" should let the user open the Prismatic market OR jump directly to
// one of its cards/products without learning which sidebar owns each entity.
export const SEARCH_ENDPOINT = "/api/market/explorer/catalog-search";
export const SEARCH_MIN_LENGTH = 2;
export const SEARCH_LIMIT = 20;
export const SEARCH_DEBOUNCE_MS = 180;
export const SEARCH_PLACEHOLDER = Object.freeze({ cards: "Search cards or markets…", sealed: "Search sealed products or markets…", graded: "Search graded cards…" });

const usable = (value) => (typeof value === "string" && value.trim() ? value.trim() : null);
const finite = (value) => Number.isFinite(Number(value)) ? Number(value) : null;
const preparedKind = (kind) => !["instrument", "graded_instrument"].includes(String(kind || ""));

export function normalizeCatalogResult(raw, requestedAsset) {
  const metadata = raw?.metadata && typeof raw.metadata === "object" ? raw.metadata : {};
  const asset = usable(raw?.asset) || requestedAsset;
  const resultKind = usable(raw?.result_kind ?? raw?.resultKind) || "instrument";
  return {
    asset,
    resultKind,
    displayName: usable(raw?.label ?? raw?.displayName) || "Unknown",
    subtitle: usable(raw?.subtitle),
    marketKey: usable(raw?.market_key ?? raw?.marketKey),
    instrumentId: usable(raw?.instrument_id ?? raw?.instrumentId),
    setId: usable(raw?.set_id ?? raw?.setId),
    eraId: usable(raw?.era_id ?? raw?.eraId),
    imageUrl: usable(raw?.image_url ?? raw?.imageUrl),
    availability: usable(raw?.availability) || "AVAILABLE",
    reason: usable(metadata.reason ?? raw?.reason),
    relevance: finite(raw?.relevance),
    metadata,
    setName: usable(metadata.setName),
    cardNumber: usable(metadata.cardNumber),
    rarity: usable(metadata.rarity),
    edition: usable(metadata.edition),
    printingType: usable(metadata.printingType),
    specialType: usable(metadata.specialType),
    productFamily: usable(metadata.productFamily),
    productType: usable(metadata.productType),
    variantLabel: usable(metadata.variantLabel),
    marketPrice: finite(metadata.marketPrice ?? metadata.latestMarketPrice ?? raw?.marketPrice),
  };
}

export function leafContext(result) {
  if (result?.subtitle) return result.subtitle;
  const parts = result?.asset === "sealed"
    ? [result?.setName, result?.variantLabel || result?.productType || result?.productFamily]
    : [result?.setName, result?.variantLabel || result?.rarity];
  return parts.filter(usable).join(" · ");
}

export function resolveSearchResultAction(result) {
  if (!result) return { primary: { kind: "none" } };
  const unavailable = String(result.availability || "").toUpperCase();
  if (result.asset === "graded" || unavailable === "INSUFFICIENT_AUTHORITY") {
    return { primary: { kind: "unavailable", reason: usable(result.reason) || "Graded search is not available yet." } };
  }
  if (preparedKind(result.resultKind) && usable(result.marketKey)) {
    if (["UNAVAILABLE", "INSUFFICIENT_AUTHORITY"].includes(unavailable)) {
      return { primary: { kind: "unavailable", reason: usable(result.reason) || "This market is not currently published." } };
    }
    return { primary: { kind: "prepared", marketKey: result.marketKey } };
  }
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
  const normalized = (Array.isArray(payload?.results) ? payload.results : []).map((row) => normalizeCatalogResult(row, asset));
  // Product rule: markets are the navigation layer, physical instruments are
  // the detail layer. Preserve backend relevance within each layer.
  return normalized.sort((a, b) => {
    const aPrepared = preparedKind(a.resultKind) && Boolean(a.marketKey);
    const bPrepared = preparedKind(b.resultKind) && Boolean(b.marketKey);
    if (aPrepared !== bPrepared) return aPrepared ? -1 : 1;
    return (b.relevance ?? -Infinity) - (a.relevance ?? -Infinity);
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
