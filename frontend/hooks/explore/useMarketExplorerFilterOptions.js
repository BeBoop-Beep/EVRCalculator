"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// One canonical taxonomy request for the Explorer workspace. Successful data
// is reusable; failures never become cache entries.
export const OPTIONS_STATUS = Object.freeze({
  loading: "loading",
  ready: "ready",
  signedOut: "signedOut",
  forbidden: "forbidden",
  unavailable: "unavailable",
  offline: "offline",
});

export const OPTIONS_RETRY_DELAYS_MS = Object.freeze([350, 850]);

export function resolveOptionsStatus(httpStatus) {
  if (httpStatus === 401) return OPTIONS_STATUS.signedOut;
  if (httpStatus === 403) return OPTIONS_STATUS.forbidden;
  return OPTIONS_STATUS.unavailable;
}

export function isRetryableOptionsFailure(result) {
  return result?.status === OPTIONS_STATUS.offline || Number(result?.httpStatus) >= 500;
}

/** FastAPI answers with `detail`; app routes answer with `message`. */
export function backendMessage(payload) {
  if (!payload || typeof payload !== "object") return "";
  if (typeof payload.message === "string") return payload.message;
  return typeof payload.detail === "string" ? payload.detail : "";
}

let inFlight = null;
let cached = null;
let cachedVersion = 0;

async function requestOptions() {
  if (!inFlight) {
    inFlight = (async () => {
      try {
        const response = await fetch("/api/market/explorer/query", {
          method: "GET",
          credentials: "include",
          cache: "no-store",
        });
        const payload = await response.json().catch(() => null);
        const result = response.ok
          ? { status: OPTIONS_STATUS.ready, options: payload, message: "", httpStatus: response.status }
          : {
              status: resolveOptionsStatus(response.status),
              options: null,
              message: backendMessage(payload),
              httpStatus: response.status,
            };
        if (result.status === OPTIONS_STATUS.ready) {
          cached = result;
          cachedVersion += 1;
        }
        return result;
      } catch {
        return { status: OPTIONS_STATUS.offline, options: null, message: "", httpStatus: null };
      } finally {
        inFlight = null;
      }
    })();
  }
  return inFlight;
}

async function loadOptions({ force = false, refreshAfterInFlight = false, acceptCachedAfterVersion = null } = {}) {
  if (acceptCachedAfterVersion !== null && cached && cachedVersion > acceptCachedAfterVersion) return cached;
  // A forced auth/profile revalidation that arrives during an older request
  // first joins it, then starts exactly one fresh request after it settles.
  if (force && inFlight) {
    const joined = await inFlight;
    if (!refreshAfterInFlight) return joined;
  }
  if (!force && cached) return cached;
  return requestOptions();
}

export function __resetMarketExplorerFilterOptionsCache() {
  cached = null;
  cachedVersion = 0;
  inFlight = null;
}

const coldState = () => cached || { status: OPTIONS_STATUS.loading, options: null, message: "", httpStatus: null };

export default function useMarketExplorerFilterOptions({
  isAuthenticated = false,
  authRevision = 0,
  enabled = true,
  retryDelays = OPTIONS_RETRY_DELAYS_MS,
} = {}) {
  const [state, setState] = useState(coldState);
  const [isRetrying, setIsRetrying] = useState(false);
  const generationRef = useRef(0);
  const timerRef = useRef(null);
  const timerResolveRef = useRef(null);
  const runningRef = useRef(null);
  const previousAuthRevisionRef = useRef(authRevision);

  const cancelPending = useCallback(() => {
    generationRef.current += 1;
    if (timerRef.current !== null) clearTimeout(timerRef.current);
    timerResolveRef.current?.();
    timerRef.current = null;
    timerResolveRef.current = null;
    runningRef.current = null;
  }, []);

  const run = useCallback((force = false, refreshAfterInFlight = false) => {
    if (!enabled) return Promise.resolve(null);
    if (runningRef.current) return runningRef.current;
    const generation = ++generationRef.current;
    const startingCacheVersion = cachedVersion;
    const knownGood = cached?.options || null;
    if (!knownGood && (!force || refreshAfterInFlight)) {
      setState((current) => ({ ...current, status: OPTIONS_STATUS.loading }));
    }
    setIsRetrying(force);

    const operation = (async () => {
      let result = null;
      for (let attempt = 0; attempt <= retryDelays.length; attempt += 1) {
        result = await loadOptions({
          force: force || attempt > 0,
          refreshAfterInFlight: refreshAfterInFlight && attempt === 0,
          acceptCachedAfterVersion: attempt > 0 ? startingCacheVersion : null,
        });
        if (generation !== generationRef.current) return null;
        if (result.status === OPTIONS_STATUS.ready || !isRetryableOptionsFailure(result)) break;
        if (attempt >= retryDelays.length) break;
        await new Promise((resolve) => {
          timerResolveRef.current = resolve;
          timerRef.current = setTimeout(() => {
            timerResolveRef.current = null;
            resolve();
          }, retryDelays[attempt]);
        });
        timerRef.current = null;
        if (generation !== generationRef.current) return null;
      }

      if (generation !== generationRef.current || !result) return null;
      if (result.status === OPTIONS_STATUS.ready) {
        setState(result);
      } else if (knownGood) {
        // Background auth/profile revalidation must never destroy usable
        // canonical filters or flash the cold-load failure UI.
        setState({ status: OPTIONS_STATUS.ready, options: knownGood, message: "", httpStatus: 200 });
      } else {
        setState(result);
      }
      return result;
    })().finally(() => {
      if (generation === generationRef.current) {
        runningRef.current = null;
        setIsRetrying(false);
      }
    });
    runningRef.current = operation;
    return operation;
  }, [enabled, retryDelays]);

  const retry = useCallback(() => run(true), [run]);

  useEffect(() => {
    if (!enabled) return cancelPending;
    const authChanged = previousAuthRevisionRef.current !== authRevision;
    previousAuthRevisionRef.current = authRevision;
    cancelPending();
    void run(authChanged && !cached, authChanged && !cached);
    return cancelPending;
  }, [authRevision, cancelPending, enabled, isAuthenticated, run]);

  return { ...state, retry, isRetrying };
}
