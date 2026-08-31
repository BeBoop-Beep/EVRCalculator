"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const PENDING_TIMEOUT_MS = 8000;
const idleState = (setId = null) => ({ status: "idle", setId, pullRateAssumptions: null, error: null });
const getPullRates = (...args) =>
  import("@/lib/pokemon/pokemonSetPullRatesClient").then((client) => client.getPokemonSetPullRates(...args));

export default function useSetPullRatesController({
  setId,
  enabled,
  canFetch,
  fallbackAssumptions = null,
}) {
  const [state, setState] = useState(() => idleState(setId));
  const [timeoutState, setTimeoutState] = useState({ setId: null, timedOut: false });
  const [retryNonce, setRetryNonce] = useState(0);
  const lastRequestKeyRef = useRef(null);
  const activeSetIdRef = useRef(setId);
  activeSetIdRef.current = setId;

  const assumptions = state.setId === setId && state.pullRateAssumptions
    ? state.pullRateAssumptions
    : fallbackAssumptions;
  const activeState = state.setId === setId ? state : idleState(setId);
  const pending = Boolean(enabled && !assumptions && (activeState.status === "idle" || activeState.status === "loading"));
  const pendingTimedOut = timeoutState.setId === setId && timeoutState.timedOut;

  useEffect(() => {
    if (!enabled || !setId || assumptions) return undefined;
    setTimeoutState((previous) =>
      previous.setId === setId && previous.timedOut ? { setId: null, timedOut: false } : previous);
    const timer = window.setTimeout(() => setTimeoutState({ setId, timedOut: true }), PENDING_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [assumptions, enabled, setId]);

  useEffect(() => {
    if (!setId) {
      setState(idleState());
      return undefined;
    }
    if (!canFetch) {
      setState((previous) => ({
        status: previous.setId === setId ? previous.status : "idle",
        setId,
        pullRateAssumptions: previous.setId === setId ? previous.pullRateAssumptions : null,
        error: null,
      }));
      return undefined;
    }
    if (!enabled) return undefined;

    const requestKey = `${setId}:${retryNonce}`;
    if (lastRequestKeyRef.current === requestKey) return undefined;
    lastRequestKeyRef.current = requestKey;
    let cancelled = false;
    let settled = false;
    setState((previous) => ({
      status: previous.setId === setId && previous.pullRateAssumptions ? "success_stale" : "loading",
      setId,
      pullRateAssumptions: previous.setId === setId ? previous.pullRateAssumptions : null,
      error: null,
    }));

    getPullRates(setId)
      .then((payload) => {
        settled = true;
        if (cancelled || activeSetIdRef.current !== setId) return;
        setState({
          status: payload?.pullRateAssumptions ? "success" : "empty",
          setId,
          pullRateAssumptions: payload?.pullRateAssumptions || null,
          error: null,
        });
      })
      .catch((error) => {
        settled = true;
        if (lastRequestKeyRef.current === requestKey) lastRequestKeyRef.current = null;
        if (cancelled || activeSetIdRef.current !== setId) return;
        setState((previous) => ({
          status: previous.setId === setId && previous.pullRateAssumptions ? "success_stale" : "error",
          setId,
          pullRateAssumptions: previous.setId === setId ? previous.pullRateAssumptions : null,
          error: error?.message || "Unable to load pull rate assumptions for this set.",
        }));
      });

    return () => {
      cancelled = true;
      if (!settled && lastRequestKeyRef.current === requestKey) lastRequestKeyRef.current = null;
    };
  }, [canFetch, enabled, retryNonce, setId]);

  const retry = useCallback(() => {
    lastRequestKeyRef.current = null;
    setRetryNonce((value) => value + 1);
  }, []);

  return { pullRateAssumptions: assumptions, activePullRatesState: activeState, pullRatesTabPending: pending, pullRatesPendingTimedOut: pendingTimedOut, retry };
}
