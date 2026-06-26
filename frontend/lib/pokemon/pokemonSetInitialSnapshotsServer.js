import { fetchWithTimeout, previewResponseBody, sanitizeBackendPath } from "@/lib/explore/explorePageServerCore.mjs";
import { normalizePokemonSetCardsPayload } from "@/lib/pokemon/pokemonSetCardsClient";
import { normalizeMarketDashboardPayload, normalizeMarketDashboardWindow } from "@/lib/pokemon/pokemonSetMarketClient";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const BACKEND_API_BASE_URL = getBackendApiBaseUrl();
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

async function loadInitialSnapshot(url, { normalizePayload, moduleName }) {
  const startedAt = Date.now();
  let response = null;

  try {
    response = await fetchWithTimeout(
      url.toString(),
      {
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store",
      },
      getTimeoutMs()
    );
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
  });
}

export async function getPokemonSetInitialSnapshots(setId) {
  const [cards, marketDashboard] = await Promise.all([
    getPokemonSetCardsInitialSnapshot(setId),
    getPokemonSetMarketDashboardInitialSnapshot(setId, { window: "365d" }),
  ]);

  const errors = {};
  if (cards.error) {
    errors.cards = cards.error;
  }
  if (marketDashboard.error) {
    errors.marketDashboard = marketDashboard.error;
  }

  return {
    cardsPayload: cards.payload,
    marketDashboardPayload: marketDashboard.payload,
    errors,
    timings: {
      cardsMs: cards.elapsedMs,
      marketDashboardMs: marketDashboard.elapsedMs,
    },
  };
}
