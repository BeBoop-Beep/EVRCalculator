import { boundedFetch, EXPLORER_REQUEST_BOUNDS_MS } from "./marketExplorerBoundedRequest.mjs";

export const MARKET_ACTIVITY_ENDPOINTS = Object.freeze({
  capabilities: "/api/market/explorer/activity/capabilities",
  group: "/api/market/explorer/activity",
  constituents: "/api/market/explorer/activity/constituents",
  instrument: "/api/market/explorer/activity/instrument",
});

export class MarketActivityApiError extends Error {
  constructor(
    message,
    { status = 0, code = "MARKET_ACTIVITY_UNAVAILABLE", payload = null } = {},
  ) {
    super(message);
    this.name = "MarketActivityApiError";
    this.status = status;
    this.code = code;
    this.payload = payload;
    this.kind =
      status === 401
        ? "auth"
        : status === 403
          ? "entitlement"
          : status === 400
            ? "invalid"
            : "unavailable";
    this.retryable = status === 0 || status >= 500;
  }
}

async function post(path, body, { signal, fetchImpl } = {}) {
  const { response, payload } = await boundedFetch(
    path,
    {
      method: "POST",
      credentials: "include",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    },
    {
      signal,
      fetchImpl,
      timeoutMs: EXPLORER_REQUEST_BOUNDS_MS.activity,
      timeoutCode: "MARKET_ACTIVITY_TIMEOUT",
      timeoutMessage: "Market Activity took too long to load. Please try again.",
      read: async (result) => {
        const text = await result.text();
        if (!text) return null;
        try {
          return JSON.parse(text);
        } catch {
          return { message: text };
        }
      },
    },
  );
  if (!response.ok) {
    const detail = payload?.detail;
    throw new MarketActivityApiError(
      payload?.message ||
        detail?.message ||
        (typeof detail === "string" ? detail : null) ||
        "Market Activity is temporarily unavailable",
      {
        status: response.status,
        code: payload?.code || detail?.code,
        payload,
      },
    );
  }
  return payload;
}

const pins = (scope) => ({
  activityGenerationId: scope.activityGenerationId,
  marketKey: scope.marketKey,
  rosterRef: scope.rosterRef,
  asOf: scope.asOf,
  windowDays: scope.windowDays,
});

export function fetchMarketActivityCapabilities({
  markets,
  windowDays = 30,
  signal,
  fetchImpl,
} = {}) {
  return post(
    MARKET_ACTIVITY_ENDPOINTS.capabilities,
    { markets, windowDays },
    { signal, fetchImpl },
  );
}

export function fetchMarketActivityGroup({
  signal,
  fetchImpl,
  chartRange = null,
  ...scope
}) {
  return post(
    MARKET_ACTIVITY_ENDPOINTS.group,
    { ...pins(scope), chartRange },
    { signal, fetchImpl },
  );
}

export function fetchMarketActivityConstituents({
  signal,
  fetchImpl,
  cursor = null,
  limit = 50,
  ...scope
}) {
  return post(
    MARKET_ACTIVITY_ENDPOINTS.constituents,
    { ...pins(scope), cursor, limit },
    { signal, fetchImpl },
  );
}

export function fetchMarketActivityInstrument({
  signal,
  fetchImpl,
  instrumentKey,
  chartRange = null,
  ...scope
}) {
  return post(
    MARKET_ACTIVITY_ENDPOINTS.instrument,
    { ...pins(scope), instrumentKey, chartRange },
    { signal, fetchImpl },
  );
}
