import { fetchWithTimeout, previewResponseBody, sanitizeBackendPath } from "@/lib/explore/explorePageServerCore.mjs";
import { normalizePokemonSetCardsPayload } from "@/lib/pokemon/pokemonSetCardsClient";
import { normalizeMarketDashboardPayload, normalizeMarketDashboardWindow } from "@/lib/pokemon/pokemonSetMarketClient";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const BACKEND_API_BASE_URL = getBackendApiBaseUrl();
const MARKET_DASHBOARD_SNAPSHOT_REVALIDATE_S = 300;
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

  return loadInitialSnapshot(url, {
    moduleName: "market dashboard",
    normalizePayload: normalizeMarketDashboardPayload,
    nextCacheOptions: { revalidate: MARKET_DASHBOARD_SNAPSHOT_REVALIDATE_S, tags: [`pokemon-set-market-dashboard:${resolvedSetId}:${normalizedWindow}`] },
  });
}

/**
 * Load the initial shell + active-tab snapshot for the Pokemon set detail page.
 *
 * Only the shell (lightweight header/title-card data) is always fetched. The
 * market dashboard snapshot is fetched only for its own tab. Cards are also
 * fetched for the insights tab: Insights' Pure Pokémon Demand vs Market Price
 * section is a Cards/checklist consumer (card rows + card appeal/market price
 * correlation), and Insights already fetches the full /page payload, which
 * doesn't carry that data — cards must be a first-class Insights dependency,
 * not a client-side backfill that leaves the section empty on first load.
 * Cards and market dashboard are still never both fetched together, since
 * only one tab is visible at a time.
 */
export async function getPokemonSetInitialSnapshots(setId, { tab } = {}) {
  const startedAt = Date.now();
  const wantsCards = tab === "cards" || tab === "insights";
  const wantsMarketDashboard = tab === "overview";

  const [shell, cards, marketDashboard] = await Promise.all([
    getPokemonSetShellInitialSnapshot(setId),
    wantsCards ? getPokemonSetCardsInitialSnapshot(setId) : Promise.resolve(EMPTY_INITIAL_SNAPSHOT),
    wantsMarketDashboard
      ? getPokemonSetMarketDashboardInitialSnapshot(setId, { window: "365d" })
      : Promise.resolve(EMPTY_INITIAL_SNAPSHOT),
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
