import { fetchWithTimeout, previewResponseBody, sanitizeBackendPath } from "@/lib/explore/explorePageServerCore.mjs";
import { normalizePokemonSetCardsPayload } from "@/lib/pokemon/pokemonSetCardsClient";
import { normalizeMarketDashboardPayload, normalizeMarketDashboardWindow } from "@/lib/pokemon/pokemonSetMarketClient";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const BACKEND_API_BASE_URL = getBackendApiBaseUrl();
const SHELL_SNAPSHOT_REVALIDATE_S = 300;
const EMPTY_INITIAL_SNAPSHOT = { payload: null, error: null, elapsedMs: 0 };
const INITIAL_SNAPSHOT_TIMEOUT_MS = Number.parseInt(
  process.env.POKEMON_SET_INITIAL_SNAPSHOT_TIMEOUT_MS || "5000",
  10
);

function getTimeoutMs() {
  return Number.isFinite(INITIAL_SNAPSHOT_TIMEOUT_MS) && INITIAL_SNAPSHOT_TIMEOUT_MS > 0
    ? INITIAL_SNAPSHOT_TIMEOUT_MS
    : 5000;
}

function serializeError(error, url, elapsedMs, status = null, bodyPreview = null) {
  return {
    message: error?.message || String(error || "Unknown snapshot load error"),
    name: error?.name || null,
    status,
    elapsedMs,
    backendPath: sanitizeBackendPath(url),
    bodyPreview,
  };
}

async function loadInitialSnapshot(url, { normalizePayload, moduleName, nextCacheOptions = null }) {
  const startedAt = Date.now();
  let response = null;

  const fetchOpts = nextCacheOptions
    ? { method: "GET", headers: { Accept: "application/json" }, next: nextCacheOptions }
    : { method: "GET", headers: { Accept: "application/json" }, cache: "no-store" };

  try {
    response = await fetchWithTimeout(url.toString(), fetchOpts, getTimeoutMs());
  } catch (error) {
    const elapsedMs = Date.now() - startedAt;
    return {
      payload: null,
      error: serializeError(error, url, elapsedMs),
      elapsedMs,
    };
  }

  const elapsedMs = Date.now() - startedAt;
  let rawText = "";
  try {
    rawText = await response.text();
  } catch (error) {
    return {
      payload: null,
      error: serializeError(error, url, elapsedMs, response.status),
      elapsedMs,
    };
  }

  if (!response.ok) {
    return {
      payload: null,
      error: serializeError(
        new Error(`${moduleName} snapshot backend error ${response.status}`),
        url,
        elapsedMs,
        response.status,
        previewResponseBody(rawText)
      ),
      elapsedMs,
    };
  }

  try {
    const payload = rawText ? JSON.parse(rawText) : null;
    return {
      payload: normalizePayload ? normalizePayload(payload || {}) : payload,
      error: null,
      elapsedMs,
    };
  } catch (error) {
    return {
      payload: null,
      error: serializeError(error, url, elapsedMs, response.status, previewResponseBody(rawText)),
      elapsedMs,
    };
  }
}

export async function getPokemonSetShellInitialSnapshot(setId) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    return {
      payload: null,
      error: { message: "Set id is required", code: "SET_ID_REQUIRED" },
      elapsedMs: 0,
    };
  }

  const url = new URL(`${BACKEND_API_BASE_URL}/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/shell`);
  return loadInitialSnapshot(url, {
    moduleName: "shell",
    nextCacheOptions: { revalidate: SHELL_SNAPSHOT_REVALIDATE_S, tags: [`pokemon-set-shell:${resolvedSetId}`] },
  });
}

export async function getPokemonSetCardsInitialSnapshot(setId) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    return {
      payload: null,
      error: { message: "Set id is required", code: "SET_ID_REQUIRED" },
      elapsedMs: 0,
    };
  }

  const url = new URL(`${BACKEND_API_BASE_URL}/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/cards`);
  // Full set card checklists can exceed Next's 2MB data-cache entry limit,
  // which fails cache writes on every request. Omitting nextCacheOptions
  // makes loadInitialSnapshot fall back to an uncached fetch instead.
  return loadInitialSnapshot(url, {
    moduleName: "cards",
    normalizePayload: normalizePokemonSetCardsPayload,
  });
}

export async function getPokemonSetMarketDashboardInitialSnapshot(setId, { window = "365d" } = {}) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    return {
      payload: null,
      error: { message: "Set id is required", code: "SET_ID_REQUIRED" },
      elapsedMs: 0,
    };
  }

  const normalizedWindow = normalizeMarketDashboardWindow(window);
  const url = new URL(`${BACKEND_API_BASE_URL}/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/market/dashboard`);
  url.searchParams.set("window", normalizedWindow);

  // Market dashboard snapshots can exceed Next's 2MB data-cache entry limit,
  // same root cause as cards (see getPokemonSetCardsInitialSnapshot). Omitting
  // nextCacheOptions makes loadInitialSnapshot fall back to an uncached fetch.
  return loadInitialSnapshot(url, {
    moduleName: "market dashboard",
    normalizePayload: normalizeMarketDashboardPayload,
  });
}

/**
 * Load the initial shell + active-tab snapshot for the Pokemon set detail page.
 *
 * Only the shell (lightweight header/title-card data) is always fetched.
 *
 * The full /cards snapshot is never route-seeded here for any tab anymore.
 * Cards uses its own slim, paginated contract (getPokemonSetCardsPage,
 * fetched client-side — see RipStatisticsPageClient.jsx). Insights' Card
 * Desirability/Market Validation section (card rows + card appeal/market
 * price correlation) now fetches the slim getPokemonSetCardsValidation
 * contract client-side instead (Phase 3C) — that endpoint reads the same
 * pokemon_set_cards_snapshot_latest row but returns only validation-ready
 * card rows, never the full checklist array. getPokemonSetCardsInitialSnapshot
 * is kept below only as a legacy helper for any caller that still needs the
 * full /cards payload server-side; getPokemonSetInitialSnapshots itself
 * never calls it.
 *
 * Overview uses /overview (+ /market/top-chase, /market/movers). Cards uses
 * /cards/page. Pull Rates uses /pull-rates (Phase 4A). Insights uses
 * /insights (Phase 4B) plus /cards/validation for its card validation
 * section — all four are fetched client-side from RipStatisticsPageClient.jsx,
 * none of them server-seeded here. The full /page snapshot is legacy-only
 * (see needsExplorePagePayload in page.js, gated on non-"set" target types
 * only) and is not part of normal set-detail initial snapshot loading.
 *
 * The monolithic /market/dashboard snapshot is never requested here anymore
 * — Overview, Top Chase Cards, and Market Movers each fetch their own slim
 * endpoint client-side (getPokemonSetOverview/getPokemonSetTopChase/
 * getPokemonSetMarketMovers in RipStatisticsPageClient.jsx) instead of
 * riding this route-level seed. marketDashboardPayload/errors.marketDashboard
 * /timings.marketDashboardMs are kept in the return shape below only for
 * backward compatibility with existing consumers that read them as an
 * optional (now always-empty) fallback — see
 * getPokemonSetMarketDashboardInitialSnapshot, which still exists for any
 * remaining legacy caller but is no longer invoked from this function.
 *
 * Cards snapshots do not use Next's data cache (nextCacheOptions) — the
 * payload can exceed the 2MB per-entry limit. Only shell uses
 * nextCacheOptions today.
 */
export async function getPokemonSetInitialSnapshots(setId, { tab } = {}) {
  const startedAt = Date.now();
  // Cards uses the paginated client endpoint (getPokemonSetCardsPage) and
  // Insights uses its own slim client-side endpoints (getPokemonSetInsights
  // plus getPokemonSetCardsValidation for card validation) — neither tab
  // needs the full /cards snapshot server-seeded anymore, so this slot
  // always resolves empty.
  const [shell, cards, marketDashboard] = await Promise.all([
    getPokemonSetShellInitialSnapshot(setId),
    Promise.resolve(EMPTY_INITIAL_SNAPSHOT),
    Promise.resolve(EMPTY_INITIAL_SNAPSHOT),
  ]);

  const totalMs = Date.now() - startedAt;
  const errors = {};
  if (shell.error) {
    errors.shell = shell.error;
  }
  if (cards.error) {
    errors.cards = cards.error;
  }
  if (marketDashboard.error) {
    errors.marketDashboard = marketDashboard.error;
  }

  console.info("[set-snapshots-server] snapshots_loaded", {
    setId,
    tab: tab || null,
    shellMs: shell.elapsedMs,
    cardsMs: cards.elapsedMs,
    marketDashboardMs: marketDashboard.elapsedMs,
    totalMs,
    shellError: Boolean(shell.error),
    cardsError: Boolean(cards.error),
    marketDashboardError: Boolean(marketDashboard.error),
  });

  return {
    shellPayload: shell.payload,
    cardsPayload: cards.payload,
    marketDashboardPayload: marketDashboard.payload,
    errors,
    timings: {
      shellMs: shell.elapsedMs,
      cardsMs: cards.elapsedMs,
      marketDashboardMs: marketDashboard.elapsedMs,
      totalMs,
    },
  };
}
