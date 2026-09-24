// ---------------------------------------------------------------------------
// Market Explorer — paginated constituents for a QUERY-BUILT market.
//
// WHY THIS EXISTS. A prepared/parent series' composition arrives already
// published and small (a capped `topConstituents` preview). A CUSTOM QUERY
// market has no such cap: Global All Raw alone is 33,955 current constituents.
// Embedding that array in the market-summary response (what building a market
// returns) would mean every "Build Market" click on a broad universe ships
// tens of thousands of row objects to the browser merely to draw a chart line.
//
// The backend already separates these concerns (Prompt 5's accepted
// architecture): the query-execution response can be requested in
// `responseMode: "summary"`, which omits `currentConstituents` entirely, and
// a dedicated `/market/explorer/query/constituents` endpoint pages the roster
// on demand, `limit` rows at a time (backend-capped at 100), keyed by the same
// normalized spec used to build the market. This module is the pure request/
// response translation for that endpoint; `useMarketExplorerConstituentPage`
// is the stateful consumer.
//
// NOTHING IS COMPUTED HERE. Rank, price and identity all come from the page
// exactly as published; this only shapes the request body and unwraps the
// response envelope (`items` / `next_cursor` / `total_constituent_count` /
// `as_of`) into a camelCase shape the rest of the frontend already expects.
// ---------------------------------------------------------------------------

export const CONSTITUENT_PAGE_ENDPOINT = "/api/market/explorer/query/constituents";

/** Structured constituent-page failure; `code` is one of the CONSTITUENT_ERROR values. */
export const CONSTITUENT_ERROR = Object.freeze({
  generationMismatch: "GENERATION_MISMATCH",
  auth: "AUTH",
  entitlement: "ENTITLEMENT",
  timeout: "TIMEOUT",
  unavailable: "UNAVAILABLE",
});

export class ConstituentPageError extends Error {
  constructor(message, { code = CONSTITUENT_ERROR.unavailable, status = 0 } = {}) {
    super(message);
    this.name = "ConstituentPageError";
    this.code = code;
    this.status = status;
  }
}

/**
 * One page of a PREPARED market's constituents, pinned to the generation the
 * market was loaded from (`identity` = { marketKey, generationId }, both
 * published by the backend on the directory row -- never inferred from labels).
 *
 * Availability states (`available` / `empty` / `unavailable` / `notApplicable`)
 * are RETURNED, not thrown: they are truthful answers the panel renders. Only
 * transport/auth/generation problems throw, with a structured `code`.
 */
export async function fetchPreparedConstituentPage(identity, { limit = 100, afterRank = 0, signal } = {}) {
  const query = new URLSearchParams({ kind: "constituents", marketKey: identity.marketKey,
    generationId: identity.generationId, limit: String(limit), afterRank: String(afterRank) });
  const response = await fetch(`/api/market/explorer/prepared?${query}`, { credentials: "include", signal });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const upper = String(payload?.code || "").toUpperCase();
    const code = response.status === 409 || upper === "GENERATION_MISMATCH" ? CONSTITUENT_ERROR.generationMismatch
      : response.status === 401 ? CONSTITUENT_ERROR.auth
        : response.status === 403 ? CONSTITUENT_ERROR.entitlement
          : response.status === 504 || upper.includes("TIMEOUT") ? CONSTITUENT_ERROR.timeout
            : CONSTITUENT_ERROR.unavailable;
    throw new ConstituentPageError("Unable to load prepared constituents", { code, status: response.status });
  }
  if (payload?.code === "GENERATION_MISMATCH") {
    throw new ConstituentPageError("Prepared generation changed", { code: CONSTITUENT_ERROR.generationMismatch, status: 409 });
  }
  return { rows: Array.isArray(payload?.rows) ? payload.rows : [], nextCursor: payload?.nextCursor ?? null,
    totalCount: payload?.totalCount || 0, asOf: payload?.priceAsOf ?? null, generationId: payload?.generationId,
    availability: payload?.availability || "unavailable", availabilityReason: payload?.availabilityReason || null,
    movementAvailable: payload?.movementAvailable === true, sourceKind: payload?.sourceKind || null };
}

/** Fetch one page. Isolated so the hook's loading state never blocks on, or
 *  gets blocked by, the main market-summary fetch — they are separate
 *  requests to separate endpoints and must be allowed to resolve out of
 *  order. */
export async function fetchConstituentPage(spec, options) {
  const response = await fetch(CONSTITUENT_PAGE_ENDPOINT, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildConstituentPageRequest(spec, options)),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      throw new Error("Sign in to view this market's constituents.");
    }
    if (response.status === 404) {
      throw new Error(payload?.message || "This market has not been built yet.");
    }
    throw new Error(payload?.message || payload?.detail || "Unable to load constituents");
  }
  return parseConstituentPageResponse(payload);
}

/** Backend hard cap, mirrored so a caller fails fast rather than on the wire. */
export const CONSTITUENT_PAGE_MAX_LIMIT = 100;
export const CONSTITUENT_PAGE_DEFAULT_LIMIT = 100;

/**
 * The request body for one page. `spec` is the SAME normalized query spec
 * that identifies the market (see marketExplorerQuery.mjs) — the backend
 * re-derives the fingerprint from it rather than trusting a client-supplied
 * one, so paging can never be pointed at a market the caller does not
 * actually hold.
 */
export function buildConstituentPageRequest(spec, { limit = CONSTITUENT_PAGE_DEFAULT_LIMIT, afterRank = 0 } = {}) {
  const boundedLimit = Math.min(Math.max(1, Number(limit) || CONSTITUENT_PAGE_DEFAULT_LIMIT), CONSTITUENT_PAGE_MAX_LIMIT);
  return {
    ...spec,
    limit: boundedLimit,
    afterRank: Math.max(0, Number(afterRank) || 0),
  };
}

/**
 * Unwrap one page response into `{ rows, nextCursor, totalCount, asOf }`.
 *
 * `nextCursor === null` means the roster is exhausted — never inferred from
 * `rows.length < limit`, which the backend states explicitly so a page that
 * happens to land exactly on the limit boundary is not mistaken for the end.
 */
export function parseConstituentPageResponse(payload) {
  const items = Array.isArray(payload?.items) ? payload.items : [];
  const nextCursorRaw = payload?.next_cursor ?? payload?.nextCursor;
  const nextCursor = Number.isFinite(Number(nextCursorRaw)) ? Number(nextCursorRaw) : null;
  const totalRaw = payload?.total_constituent_count ?? payload?.totalConstituentCount;
  return {
    rows: items,
    nextCursor,
    totalCount: Number.isFinite(Number(totalRaw)) ? Number(totalRaw) : items.length,
    asOf: payload?.as_of ?? payload?.asOf ?? null,
  };
}

/** Append a fetched page to what is already held, de-duplicated by rank. */
export function appendConstituentPage(existingRows, page) {
  const seenRanks = new Set(existingRows.map((row) => row?.rank));
  const additions = page.rows.filter((row) => {
    if (seenRanks.has(row?.rank)) return false;
    seenRanks.add(row?.rank);
    return true;
  });
  return [...existingRows, ...additions];
}
