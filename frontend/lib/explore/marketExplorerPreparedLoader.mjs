// ---------------------------------------------------------------------------
// Market Explorer — prepared-market selection lifecycle.
//
// ONE STATE MACHINE FOR EVERY ENTRY POINT (Sets, Eras, Quick Markets, Rarity,
// Sealed, Screens results). A market is in exactly one of four states:
//
//   IDLE  -> LOADING (pending) -> LOADED (active on the chart)
//                              -> FAILED (recoverable: retry / dismiss)
//
// "Active" means LOADED. A click never makes a market active by itself; the
// separate `pending` and `failed` sets carry "requested" and "did not load", so
// nothing has to overload one list to mean two things (the previous single
// `preparedActiveKeys` list did, and one failed key was then re-sent with every
// later request, poisoning all subsequent selections).
//
// FETCH ARCHITECTURE (decision B, see docs/MARKET_EXPLORER_BUCKET2A_PREPARED_SELECTION.md):
// each market is fetched INDEPENDENTLY (one prepared comparison row + its own
// history per market; the backend computes every field per market, so nothing
// here recomputes finance or needs a shared comparison). Adding a market fetches
// only that market; removing is local; a failure affects only the market that
// failed; already-loaded histories are never refetched.
//
// STALE-RESPONSE SAFETY. Every request carries a per-key token. Removal,
// supersession, Clear and dispose invalidate the token, so a response that
// lands late (or out of order) is dropped: it can neither resurrect a removed
// market nor overwrite a newer request's result. AbortError is never an error.
//
// Pure module: no React, no network of its own. `fetchMarket` is injected.
// ---------------------------------------------------------------------------

export const PREPARED_MARKET_LIMIT = 25;
export const PREPARED_REQUEST_TIMEOUT_MS = 20000;

export const PREPARED_FAILURE = Object.freeze({
  auth: "AUTH",
  entitlement: "ENTITLEMENT",
  unavailable: "UNAVAILABLE",
  timeout: "TIMEOUT",
  invalidKey: "INVALID_KEY",
  transient: "TRANSIENT",
});

const COPY = {
  [PREPARED_FAILURE.auth]: "Sign in to compare markets.",
  [PREPARED_FAILURE.entitlement]: "Comparing markets is included with Index+.",
  [PREPARED_FAILURE.timeout]: "took too long to load.",
  [PREPARED_FAILURE.invalidKey]: "is not a published market.",
  [PREPARED_FAILURE.unavailable]: "is temporarily unavailable.",
  [PREPARED_FAILURE.transient]: "could not be loaded. Check your connection and retry.",
};

/**
 * Structured failure. Authentication/entitlement are NOT transient outages and
 * must not read as one; retrying them is pointless, so `retryable` is false.
 */
export function classifyPreparedFailure({ status = 0, code = "", timedOut = false } = {}) {
  const upper = String(code || "").toUpperCase();
  let kind = PREPARED_FAILURE.transient;
  if (timedOut || status === 504 || upper.includes("TIMEOUT")) kind = PREPARED_FAILURE.timeout;
  else if (status === 401) kind = PREPARED_FAILURE.auth;
  else if (status === 403) kind = PREPARED_FAILURE.entitlement;
  else if (status === 400 || status === 404 || upper === "PREPARED_MARKET_UNKNOWN" || upper === "PREPARED_COMPARISON_INVALID") kind = PREPARED_FAILURE.invalidKey;
  else if (status === 503 || upper.includes("UNAVAILABLE") || upper.includes("FAILED")) kind = PREPARED_FAILURE.unavailable;
  return { kind, retryable: kind !== PREPARED_FAILURE.auth && kind !== PREPARED_FAILURE.entitlement && kind !== PREPARED_FAILURE.invalidKey };
}

/** Concise user copy naming the failed market when it is known. Never raw SQL/PostgREST text. */
export function describePreparedFailure(label, failure) {
  const name = label || "This market";
  const text = COPY[failure?.kind] || COPY[PREPARED_FAILURE.transient];
  if (failure?.kind === PREPARED_FAILURE.auth || failure?.kind === PREPARED_FAILURE.entitlement) return text;
  return `${name} ${text}`;
}

/** Error carrying enough structure for the classifier; thrown by fetchers. */
export class PreparedFetchError extends Error {
  constructor(message, { status = 0, code = "" } = {}) {
    super(message);
    this.name = "PreparedFetchError";
    this.status = status;
    this.code = code;
  }
}

const isAbort = (error) => error?.name === "AbortError";

export function createPreparedMarketLoader({
  fetchMarket,
  limit = PREPARED_MARKET_LIMIT,
  timeoutMs = PREPARED_REQUEST_TIMEOUT_MS,
  setTimer = (fn, ms) => setTimeout(fn, ms),
  clearTimer = (id) => clearTimeout(id),
} = {}) {
  if (typeof fetchMarket !== "function") throw new TypeError("fetchMarket is required");

  let sequence = 0;
  let state = { order: [], loaded: {}, pending: [], failed: {}, revision: 0 };
  const tokens = new Map(); // key -> token of the ONLY request allowed to settle it
  const controllers = new Map();
  const timers = new Map();
  const listeners = new Set();
  // Key -> keys to drop once this (replacement) request succeeds.
  const replaces = new Map();

  const emit = (patch) => {
    state = { ...state, ...patch, revision: state.revision + 1 };
    for (const listener of [...listeners]) listener();
  };
  const cancel = (key) => {
    tokens.delete(key);
    replaces.delete(key);
    if (timers.has(key)) { clearTimer(timers.get(key)); timers.delete(key); }
    const controller = controllers.get(key);
    controllers.delete(key);
    if (controller) controller.abort();
  };
  const without = (record, keys) => {
    const next = { ...record };
    for (const key of keys) delete next[key];
    return next;
  };

  function begin(key, { replaceOthers = false } = {}) {
    if (state.loaded[key] || state.pending.includes(key)) return Promise.resolve("duplicate");
    if (!replaceOthers && state.order.filter((k) => state.loaded[k] || state.pending.includes(k)).length >= limit) {
      return Promise.resolve("limit");
    }
    const token = ++sequence;
    const controller = new AbortController();
    tokens.set(key, token);
    controllers.set(key, controller);
    let timedOut = false;
    const timer = setTimer(() => { timedOut = true; controller.abort(); }, timeoutMs);
    timers.set(key, timer);
    // Context keys are NEVER read by the backend; they only let the Index+
    // compare entitlement judge the whole workspace.
    // REPLACEMENT IS NOT COMPARISON: a replace request must never carry the line it
    // is about to swap out, or the backend counts two unique keys as a comparison.
    const contextKeys = replaceOthers
      ? []
      : state.order.filter((k) => k !== key && (state.loaded[k] || state.pending.includes(k)));
    if (replaceOthers) {
      // A superseded in-flight request must not later land; loaded lines stay
      // until the replacement succeeds, so a failed swap leaves the chart intact.
      for (const other of state.pending) if (other !== key) cancel(other);
      replaces.set(key, true);
    }
    const nextPending = replaceOthers ? [key] : [...state.pending, key];
    emit({
      order: state.order.includes(key) ? state.order : [...state.order, key],
      pending: nextPending,
      failed: without(state.failed, [key]),
    });

    return Promise.resolve()
      .then(() => fetchMarket(key, { contextKeys, signal: controller.signal }))
      .then((series) => {
        clearTimer(timer);
        if (tokens.get(key) !== token) return "stale";
        tokens.delete(key);
        timers.delete(key);
        controllers.delete(key);
        const swap = replaces.get(key);
        replaces.delete(key);
        const dropped = swap ? state.order.filter((k) => k !== key) : [];
        emit({
          order: swap ? [key] : state.order,
          pending: state.pending.filter((k) => k !== key),
          loaded: { ...(swap ? {} : state.loaded), [key]: series },
          failed: swap ? {} : without(state.failed, [key]),
        });
        for (const gone of dropped) cancel(gone);
        return "loaded";
      })
      .catch((error) => {
        clearTimer(timer);
        if (tokens.get(key) !== token) return "stale";
        if (isAbort(error) && !timedOut) return "stale";
        tokens.delete(key);
        timers.delete(key);
        controllers.delete(key);
        replaces.delete(key);
        const failure = classifyPreparedFailure({ status: error?.status, code: error?.code, timedOut });
        emit({
          pending: state.pending.filter((k) => k !== key),
          // A market that never loaded leaves the workspace order entirely.
          order: state.loaded[key] ? state.order : state.order.filter((k) => k !== key),
          failed: { ...state.failed, [key]: failure },
        });
        return "failed";
      });
  }

  const api = {
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    getSnapshot: () => state,
    /** Request a market. Resolves 'loaded' | 'failed' | 'duplicate' | 'limit' | 'stale'. */
    add: (key) => begin(key),
    /** Basic plan: one market at a time; the previous line stays until this one loads. */
    replace(key) {
      if (state.loaded[key]) {
        for (const other of state.order) if (other !== key) api.remove(other);
        return Promise.resolve("duplicate");
      }
      return begin(key, { replaceOthers: true });
    },
    retry: (key) => begin(key),
    /** Remove a loaded OR pending market; a late response is ignored. */
    remove(key) {
      cancel(key);
      emit({
        order: state.order.filter((k) => k !== key),
        pending: state.pending.filter((k) => k !== key),
        loaded: without(state.loaded, [key]),
        failed: without(state.failed, [key]),
      });
    },
    /** Hide a failure without touching any loaded market. */
    dismissFailure(key) { if (state.failed[key]) emit({ failed: without(state.failed, [key]) }); },
    /** Re-fetch one already-loaded market (prepared generation changed); keeps the old line on failure. */
    async refresh(key) {
      if (!state.loaded[key]) return "missing";
      const token = ++sequence;
      tokens.set(`refresh:${key}`, token);
      try {
        const series = await fetchMarket(key, { contextKeys: [], signal: undefined });
        if (tokens.get(`refresh:${key}`) !== token || !state.loaded[key]) return "stale";
        emit({ loaded: { ...state.loaded, [key]: series } });
        return "refreshed";
      } catch {
        return "failed";
      }
    },
    clear() {
      for (const key of [...controllers.keys()]) cancel(key);
      tokens.clear();
      replaces.clear();
      emit({ order: [], loaded: {}, pending: [], failed: {} });
    },
    dispose() { api.clear(); listeners.clear(); },
  };
  return api;
}

/** Loaded series in the user's request order (never completion order). */
export function loadedPreparedSeries(snapshot) {
  return snapshot.order.map((key) => snapshot.loaded[key]).filter(Boolean);
}
