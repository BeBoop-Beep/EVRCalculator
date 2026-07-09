"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const IDLE_STATE = { status: "idle", setId: null, data: null, error: null };

// Generalizes the {status, setId, data, error} shape already proven by
// RipStatisticsPageClient.jsx's pullRatesState — including the setId-match
// guard that keeps a stale response from a previous set from rendering after
// a set switch. Uses a monotonically-increasing request id to ignore stale
// responses (matching this codebase's existing convention of ignore-if-stale
// rather than AbortController, e.g. pokemonSetInsightsClient.js's in-flight
// join map).
//
// fetcher: (setId) => Promise<data>
export function useSectionFetchState(fetcher, { setId, enabled = true } = {}) {
  const [state, setState] = useState(IDLE_STATE);
  const requestIdRef = useRef(0);
  // Auto-fetch dedupe: the enabled/setId effect below re-runs on every tab
  // revisit (enabled toggles false -> true) and on StrictMode's double effect
  // invocation, which used to re-issue an identical request each time. This
  // ref claims a setId when its auto-fetch is issued and only releases it on
  // error (so a revisit can retry) — an in-flight or succeeded fetch for the
  // same set is never repeated automatically. refetch() bypasses it on
  // purpose (explicit user retry).
  const autoFetchedSetIdRef = useRef(null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const runFetch = useCallback((targetSetId) => {
    if (!targetSetId) {
      return;
    }
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;

    setState((prev) => ({
      status: "loading",
      setId: targetSetId,
      data: prev.setId === targetSetId ? prev.data : null,
      error: null,
    }));

    Promise.resolve()
      .then(() => fetcherRef.current(targetSetId))
      .then((data) => {
        if (requestIdRef.current !== requestId) {
          return;
        }
        setState({ status: "success", setId: targetSetId, data, error: null });
      })
      .catch((error) => {
        if (requestIdRef.current !== requestId) {
          return;
        }
        if (autoFetchedSetIdRef.current === targetSetId) {
          autoFetchedSetIdRef.current = null;
        }
        setState((prev) => ({
          status: "error",
          setId: targetSetId,
          data: prev.setId === targetSetId ? prev.data : null,
          error,
        }));
      });
  }, []);

  useEffect(() => {
    if (!enabled || !setId) {
      return;
    }
    if (autoFetchedSetIdRef.current === setId) {
      return;
    }
    autoFetchedSetIdRef.current = setId;
    runFetch(setId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, setId, runFetch]);

  const refetch = useCallback(() => {
    if (setId) {
      autoFetchedSetIdRef.current = setId;
      runFetch(setId);
    }
  }, [setId, runFetch]);

  return { state, refetch };
}
