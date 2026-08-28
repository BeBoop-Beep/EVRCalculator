// Shared query/timeout contract for the slim Pokemon set module proxies
// (/overview, /market/top-chase, /market/movers, /market/value-history).
//
// Why this module exists: each of those four Next routes hand-rolled its own
// param forwarding, and they drifted out of sync with the browser client in
// lib/pokemon/pokemonSetMarketClient.js. Two drops were live on this branch:
//
//   - getPokemonSetOverview sends snapshot_contract; the overview proxy never
//     forwarded it.
//   - getPokemonSetMarketMovers sends movement; the movers proxy never
//     forwarded it.
//
// Keeping the forwarded-parameter allowlist in one table next to the backend
// path makes browser request, Next proxy request, and backend request agree by
// construction instead of by four separate copies of the same if-block.
//
// This module is intentionally free of any next/server import so the contract
// can be unit-tested directly.

// Conservative bound on a stalled backend read. The four slim module proxies
// previously awaited fetch() with no timeout at all: a backend read that never
// answered left the browser request pending forever, which stranded the
// Overview section on its skeleton *and* pinned the client's shared in-flight
// promise (slimModuleInflight in pokemonSetMarketClient.js is only cleared in
// .finally()), so no later visit or retry could ever start a fresh request.
//
// 12s sits above the slowest healthy slim read for these endpoints and below
// the point where a user has already read the section as broken. The sibling
// proxies that already had a bound use the same AbortController +
// BACKEND_FETCH_TIMEOUT_MS shape (/page = 9s, /cards = 15s).
export const BACKEND_FETCH_TIMEOUT_MS = 12_000;

export const PUBLIC_ANALYTICS_CACHE_CONTROL = "public, s-maxage=300, stale-while-revalidate=3600";
export const FAILED_ANALYTICS_CACHE_CONTROL = "no-store";
export const UNCACHED_ANALYTICS_CACHE_CONTROL = "no-store";

// Per-module success cache policy.
//
// The shared `public, s-maxage=300, stale-while-revalidate=3600` policy is
// correct for modules whose payload only moves when the daily publication moves
// it. It is NOT correct for /overview: Overview carries the Opening Profit vs
// Cost history, and stale-while-revalidate=3600 lets an edge/CDN keep answering
// with a payload whose OPvC series ends on the previous market date for up to an
// hour AFTER the market-dashboard row has been rebuilt for the new one. The
// user-visible symptom is an Overview stuck a day behind a database that is
// already current.
//
// Overview therefore opts out of shared caching entirely. Correctness of the
// freshest published date beats a 5-minute edge hit on the one module whose
// staleness is the defect being repaired. Every other module keeps its existing
// policy unchanged.
//
// top-chase opts out for the same class of reason. It is a slim request whose
// payload must agree with the promoted market date, and replaying an incomplete
// or previous-generation Top Chase response for up to an hour is exactly how the
// section ends up showing cards whose charts all read "Awaiting trend". The
// client validates every response against the dedicated payload contract and
// keeps its own validated last-known-good copy, so correctness here is worth
// more than a 5-minute edge hit. Cache-busting query parameters are deliberately
// NOT used — the request stays cacheable-by-identity, it is simply not cached.
const SUCCESS_CACHE_CONTROL_BY_MODULE = Object.freeze({
  overview: UNCACHED_ANALYTICS_CACHE_CONTROL,
  "top-chase": UNCACHED_ANALYTICS_CACHE_CONTROL,
});

/**
 * Cache-Control for a slim module response. Failures are always no-store;
 * successes use the module's declared policy, defaulting to the shared public
 * analytics policy.
 */
export function resolveSlimSetModuleCacheControl(moduleKey, { ok } = {}) {
  if (!ok) {
    return FAILED_ANALYTICS_CACHE_CONTROL;
  }
  return SUCCESS_CACHE_CONTROL_BY_MODULE[moduleKey] || PUBLIC_ANALYTICS_CACHE_CONTROL;
}

// Each entry declares the backend sub-path and the exact query params the
// proxy forwards. A param is either a plain name (forwarded unchanged) or
// { from: [...incoming aliases], to: backendName } for a deliberate rename.
//
// Nothing here changes contract-version constants, window meanings, ranking or
// limit semantics: the proxy forwards the client's values through untouched.
export const SLIM_SET_MODULE_PROXY_CONTRACTS = Object.freeze({
  overview: {
    backendPath: "overview",
    moduleLabel: "set overview",
    codePrefix: "POKEMON_SET_OVERVIEW",
    forwardParams: ["window", "snapshot_contract"],
  },
  "top-chase": {
    backendPath: "market/top-chase",
    moduleLabel: "set top chase cards",
    codePrefix: "POKEMON_SET_TOP_CHASE",
    forwardParams: ["window", "limit", "snapshot_contract"],
  },
  movers: {
    backendPath: "market/movers",
    moduleLabel: "set market movers",
    codePrefix: "POKEMON_SET_MARKET_MOVERS",
    // movement=all|heating|cooling is part of the shared canonical Cards
    // query contract the backend reads (see get_pokemon_set_market_movers).
    forwardParams: ["window", "limit", "movement", "snapshot_contract"],
  },
  sealed: {
    backendPath: "market/sealed",
    moduleLabel: "set sealed market history",
    codePrefix: "POKEMON_SET_SEALED_MARKET",
    forwardParams: [],
  },
  "sealed-consumer": {
    backendPath: "market/sealed-consumer",
    moduleLabel: "set consumer sealed market",
    codePrefix: "POKEMON_SET_CONSUMER_SEALED",
    forwardParams: [],
  },
  "value-history": {
    backendPath: "market/value-history",
    moduleLabel: "set value history",
    codePrefix: "POKEMON_SET_VALUE_HISTORY",
    // The backend parameter is value_scope; the client sends scope. This
    // rename predates this module and is preserved exactly.
    forwardParams: ["days", { from: ["value_scope", "scope"], to: "value_scope" }, "snapshot_contract"],
  },
});

export function getSlimSetModuleProxyContract(moduleKey) {
  const contract = SLIM_SET_MODULE_PROXY_CONTRACTS[moduleKey];
  if (!contract) {
    throw new Error(`Unknown slim set module proxy contract: ${moduleKey}`);
  }
  return contract;
}

function readParam(searchParams, name) {
  if (!searchParams) {
    return null;
  }
  const value = typeof searchParams.get === "function" ? searchParams.get(name) : null;
  return value === null || value === undefined || value === "" ? null : value;
}

/**
 * Resolve the forwarded query params for one module as ordered [name, value]
 * pairs. Absent/empty incoming params are omitted so the backend keeps its own
 * defaults (e.g. movement -> "all") rather than receiving an empty string.
 */
export function resolveForwardedQueryParams(moduleKey, searchParams) {
  const { forwardParams } = getSlimSetModuleProxyContract(moduleKey);
  const resolved = [];

  forwardParams.forEach((param) => {
    if (typeof param === "string") {
      const value = readParam(searchParams, param);
      if (value !== null) {
        resolved.push([param, value]);
      }
      return;
    }
    const aliases = Array.isArray(param?.from) ? param.from : [];
    for (const alias of aliases) {
      const value = readParam(searchParams, alias);
      if (value !== null) {
        resolved.push([param.to, value]);
        return;
      }
    }
  });

  return resolved;
}

export function buildSlimSetModuleBackendUrl({ baseUrl, moduleKey, setId, searchParams }) {
  const { backendPath } = getSlimSetModuleProxyContract(moduleKey);
  const backendUrl = new URL(`${baseUrl}/tcgs/pokemon/sets/${encodeURIComponent(setId)}/${backendPath}`);
  resolveForwardedQueryParams(moduleKey, searchParams).forEach(([name, value]) => {
    backendUrl.searchParams.set(name, value);
  });
  return backendUrl;
}

export function isAbortError(error) {
  return error?.name === "AbortError" || String(error?.message || "").toLowerCase().includes("abort");
}

/**
 * Structured body for a proxy-level failure. `retryable: true` is what lets the
 * Overview sections offer a section-local Retry instead of shimmering forever.
 */
export function buildSlimSetModuleProxyErrorBody({ moduleKey, setId, timedOut, backendPath = null }) {
  const { moduleLabel, codePrefix } = getSlimSetModuleProxyContract(moduleKey);
  return {
    message: timedOut ? `${moduleLabel} request timed out` : `Unable to load ${moduleLabel}`,
    code: timedOut ? `${codePrefix}_PROXY_TIMEOUT` : `${codePrefix}_PROXY_ERROR`,
    retryable: true,
    setId: setId || null,
    ...(backendPath ? { backendPath } : {}),
  };
}

export function slimSetModuleProxyErrorStatus(timedOut) {
  return timedOut ? 504 : 502;
}
