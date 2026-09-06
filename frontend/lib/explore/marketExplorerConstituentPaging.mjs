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
  const additions = page.rows.filter((row) => !seenRanks.has(row?.rank));
  return [...existingRows, ...additions];
}
