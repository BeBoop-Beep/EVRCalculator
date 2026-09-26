// ---------------------------------------------------------------------------
// Market Explorer — contextual catalog search (pure logic, no React).
//
// ONE search field, scoped by the active BROWSE asset (Cards | Sealed | Graded).
// The controller owns debounce, AbortController and stale-response protection so
// a late response can never overwrite a newer query, and a failure is retryable.
//
// Result contract (from search_pokemon_market_explorer_catalog_v1 through the
// backend route): asset, result_kind, label, subtitle, market_key, instrument_id,
// set_id, era_id, image_url, availability, metadata, relevance.
//
// A result is EITHER an aggregate market (market_key) OR a leaf instrument.
// An instrument is never presented as an aggregate market.
// ---------------------------------------------------------------------------
import { resolveConstituentDetailHref } from "./marketExplorerConstituentPresentation.mjs";

export const SEARCH_ENDPOINT = "/api/market/explorer/catalog-search";
export const SEARCH_MIN_LENGTH = 2;
export const SEARCH_LIMIT = 12; // bounded list; backend cap is 50
export const SEARCH_DEBOUNCE_MS = 250; // within the 200-300ms contract

export const SEARCH_PLACEHOLDER = Object.freeze({
  cards: "Search cards, Sets, Eras, rarities, and card markets…",
  sealed: "Search sealed products, Sets, Eras, and sealed markets…",
  graded: "Search graded cards…",
});

export const RESULT_KIND_LABEL = Object.freeze({
  prepared_market: "Market",
  set: "Set",
  era: "Era",
  rarity: "Rarity",
  sealed_type: "Sealed type",
  instrument: "Card / Product",
  graded_instrument: "Graded",
});

export function resultKindLabel(result) {
  if (result?.result_kind === "instrument") return result?.asset === "sealed" ? "Product" : "Card";
  return RESULT_KIND_LABEL[result?.result_kind] || "Result";
}

const usable = (value) => (typeof value === "string" && value.trim() ? value.trim() : null);
const isUnavailable = (result) => {
  const state = String(result?.availability || "").toUpperCase();
  return Boolean(state) && state !== "AVAILABLE" && state !== "PREPARED";
};

/**
 * The action(s) a result offers. Pure and identity-driven.
 *  - market_key present      -> primary "activate" through the SAME prepared
 *                               loader Browse uses (no second activation path)
 *  - instrument              -> primary "detail" (existing detail-href resolver),
 *                               secondary "basket" (existing Exact Basket pathway)
 *  - graded / no authority   -> "unavailable" with the DB-published reason
 */
export function resolveSearchResultAction(result) {
  if (!result) return { primary: { kind: "none" }, secondary: null };
  const metadata = result.metadata && typeof result.metadata === "object" ? result.metadata : {};
  if (result.asset === "graded" || String(result.availability || "").toUpperCase() === "INSUFFICIENT_AUTHORITY") {
    return { primary: { kind: "unavailable", reason: usable(result.subtitle) || "Graded markets are not available yet." }, secondary: null };
  }
  if (usable(result.market_key)) {
    if (isUnavailable(result)) {
      return { primary: { kind: "unavailable", reason: usable(result.subtitle) || "This market is not available right now." }, secondary: null };
    }
    return { primary: { kind: "activate", marketKey: result.market_key.trim() }, secondary: null };
  }
  if (result.result_kind === "instrument" && usable(result.instrument_id)) {
    const row = result.asset === "sealed"
      ? { sealedProductId: metadata.sealedProductId || result.instrument_id }
      : { canonicalCardId: metadata.canonicalCardId, cardVariantId: metadata.cardVariantId || result.instrument_id, setId: result.set_id, setName: metadata.setName };
    // A card detail link needs the canonical card identity. It is never inferred from
    // the label, search text, variant id or a per-result lookup: absent -> no link.
    const href = result.asset === "sealed" || usable(metadata.canonicalCardId) ? resolveConstituentDetailHref(row) : null;
    const item = result.asset === "sealed"
      ? { asset: "sealed", instrumentId: result.instrument_id, name: result.label, setName: metadata.setName, productFamily: metadata.productFamily, variantLabel: metadata.variantLabel, imageUrl: result.image_url }
      : { asset: "cards", instrumentId: result.instrument_id, name: result.label, cardNumber: metadata.cardNumber, rarity: metadata.rarity, edition: metadata.edition, printingType: metadata.printingType, specialType: metadata.specialType, imageUrl: result.image_url };
    return {
      primary: href ? { kind: "detail", href } : { kind: "none", reason: "Detail page link is not available for this card yet." },
      secondary: isUnavailable(result) ? null : { kind: "basket", item },
    };
  }
  return { primary: { kind: "none" }, secondary: null };
}

export async function fetchCatalogSearch({ asset, q, limit = SEARCH_LIMIT, signal }) {
  const query = new URLSearchParams({ asset, q, limit: String(limit) });
  const response = await fetch(`${SEARCH_ENDPOINT}?${query}`, { credentials: "include", cache: "no-store", signal });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error("Search is temporarily unavailable");
    error.status = response.status;
    error.code = payload?.code || "CATALOG_SEARCH_FAILED";
    throw error;
  }
  return Array.isArray(payload?.results) ? payload.results : [];
}

const isAbort = (error) => error?.name === "AbortError";

/**
 * Debounced, abortable, stale-safe search state machine.
 * state: { status: idle|loading|ready|error, query, asset, results, error }
 */
export function createCatalogSearchController({
  fetchResults = fetchCatalogSearch,
  debounceMs = SEARCH_DEBOUNCE_MS,
  limit = SEARCH_LIMIT,
  minLength = SEARCH_MIN_LENGTH,
  setTimer = (fn, ms) => setTimeout(fn, ms),
  clearTimer = (id) => clearTimeout(id),
} = {}) {
  let state = { status: "idle", query: "", asset: "cards", results: [], error: null };
  let token = 0;
  let timer = null;
  let controller = null;
  const listeners = new Set();
  const emit = (patch) => { state = { ...state, ...patch }; for (const l of [...listeners]) l(); };
  const cancelInflight = () => {
    if (timer != null) { clearTimer(timer); timer = null; }
    if (controller) { controller.abort(); controller = null; }
  };

  function run(query, asset) {
    const mine = ++token;
    cancelInflight();
    const needle = String(query || "").trim();
    if (needle.length < minLength) { emit({ status: "idle", query: needle, asset, results: [], error: null }); return; }
    emit({ status: "loading", query: needle, asset, error: null });
    timer = setTimer(async () => {
      timer = null;
      controller = new AbortController();
      const mineController = controller;
      try {
        const results = await fetchResults({ asset, q: needle, limit, signal: mineController.signal });
        if (mine !== token) return; // stale: a newer query or asset switch superseded this one
        controller = null;
        emit({ status: "ready", results: (Array.isArray(results) ? results : []).slice(0, limit), error: null });
      } catch (error) {
        if (mine !== token || isAbort(error)) return;
        controller = null;
        emit({ status: "error", results: [], error: { code: error?.code || "CATALOG_SEARCH_FAILED", status: error?.status || 0 } });
      }
    }, debounceMs);
  }

  return {
    subscribe(l) { listeners.add(l); return () => listeners.delete(l); },
    getSnapshot: () => state,
    /** Type into the field (or switch asset: same call with the new asset). */
    search: (query, asset = state.asset) => run(query, asset),
    /** Re-run the current query after a failure. */
    retry: () => run(state.query, state.asset),
    clear() { token += 1; cancelInflight(); emit({ status: "idle", query: "", results: [], error: null }); },
    dispose() { token += 1; cancelInflight(); listeners.clear(); },
  };
}
