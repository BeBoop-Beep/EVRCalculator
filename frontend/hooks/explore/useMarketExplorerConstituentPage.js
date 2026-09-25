"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  appendConstituentPage,
  fetchConstituentPage,
  fetchPreparedConstituentPage,
  CONSTITUENT_PAGE_DEFAULT_LIMIT,
} from "@/lib/explore/marketExplorerConstituentPaging.mjs";
import { constituentPageCacheKey } from "@/lib/explore/marketExplorerWorkspace.mjs";

const IDLE = {
  rows: [], totalCount: 0, nextCursor: null, asOf: null, availability: null, availabilityReason: null,
  movementAvailable: false, key: null,
};

/**
 * Incrementally loaded constituents for ONE market: either a query-built market
 * (identified by its spec) or a PREPARED market (identified by
 * `{ marketKey, generationId }`, published by the backend).
 *
 * DELIBERATELY SEPARATE FROM THE MARKET-SUMMARY FETCH. Building a market (or
 * toggling which chart series is visible) never touches this hook; it only
 * runs when the Constituents section is actually inspecting a market, and its
 * own loading/error state never blocks the chart, the legend or Active Markets.
 *
 * NEVER HOLDS THE WHOLE ROSTER AT ONCE UNLESS THE USER ASKS FOR IT PAGE BY
 * PAGE. Each `loadMore()` appends one backend page (<=100 rows).
 *
 * STALE SAFETY. Every request takes a sequence number; only the newest request
 * for the current identity may settle state, so a response for a previous
 * market, a superseded retry, or a page that lands after the identity changed is
 * dropped. A failed page keeps the rows already loaded and `retry()` re-issues
 * the SAME cursor.
 */
export default function useMarketExplorerConstituentPage(spec, { limit = CONSTITUENT_PAGE_DEFAULT_LIMIT, autoLoad = true, cache = null } = {}) {
  const [rawState, setState] = useState(IDLE);
  const [status, setStatus] = useState("idle"); // idle | loading | loadingMore | ready | error
  const [error, setError] = useState(null);
  const [errorCode, setErrorCode] = useState(null);
  // Which identity the current error belongs to, so a consumer never acts on an
  // error left over from the previous market/generation during the re-render
  // that follows an identity change.
  const [errorSpecKey, setErrorSpecKey] = useState(null);
  const sequenceRef = useRef(0);
  const lastAttemptRef = useRef({ afterRank: 0, appending: false });

  const specKey = spec ? JSON.stringify(spec) : null;
  // GENERATION-PINNED CACHE KEY (generationId + marketKey for prepared markets).
  // State is only ever exposed for the identity it was loaded for, so a late
  // response or a stale render for the previous target can never be displayed.
  const cacheKey = constituentPageCacheKey(spec);
  const state = rawState.key === cacheKey ? rawState : IDLE;

  const load = useCallback(async (afterRank, { appending }) => {
    if (!spec) return;
    const sequence = ++sequenceRef.current;
    lastAttemptRef.current = { afterRank, appending };
    setStatus(appending ? "loadingMore" : "loading");
    setError(null);
    setErrorCode(null);
    try {
      const page = spec.marketKey
        ? await fetchPreparedConstituentPage(spec, { limit, afterRank })
        : await fetchConstituentPage(spec, { limit, afterRank });
      // A newer request (or a different market) owns the state now.
      if (sequenceRef.current !== sequence) return;
      setState((current) => ({
        key: cacheKey,
        rows: appending ? appendConstituentPage(current.key === cacheKey ? current.rows : [], page) : page.rows,
        totalCount: page.totalCount,
        nextCursor: page.nextCursor,
        asOf: page.asOf,
        availability: page.availability || "available",
        availabilityReason: page.availabilityReason || null,
        movementAvailable: page.movementAvailable === true,
      }));
      setStatus("ready");
    } catch (exc) {
      if (sequenceRef.current !== sequence) return;
      if (exc?.code === "GENERATION_MISMATCH") {
        // Invalidate ONLY the affected generation/target; other targets keep their pages.
        setState(IDLE);
        cache?.delete(cacheKey);
      }
      setError(exc instanceof Error ? exc.message : "Unable to load constituents");
      setErrorCode(exc?.code || null);
      setErrorSpecKey(specKey);
      setStatus("error");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [specKey, limit]);

  useEffect(() => {
    // Invalidate anything still in flight for the previous identity.
    sequenceRef.current += 1;
    setState(IDLE);
    setError(null);
    setErrorCode(null);
    setStatus("idle");
    // A valid cached target (same generation + market) is restored, not refetched.
    const cached = cache?.get(cacheKey);
    if (spec && cached) { setState(cached); setStatus("ready"); return; }
    if (spec && autoLoad) load(0, { appending: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [specKey, autoLoad]);

  // Remember every settled page set for this identity, so A -> B -> A is free.
  useEffect(() => {
    if (cache && status === "ready" && rawState.key && rawState.key === cacheKey) cache.set(cacheKey, rawState);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rawState, status]);

  const loadMore = useCallback(() => {
    if (state.nextCursor === null || status === "loading" || status === "loadingMore") return;
    load(state.nextCursor, { appending: true });
  }, [load, state.nextCursor, status]);

  const reload = useCallback(() => load(0, { appending: false }), [load]);
  /** Re-issue exactly the request that failed (same cursor). */
  const retry = useCallback(() => load(lastAttemptRef.current.afterRank, { appending: lastAttemptRef.current.appending }), [load]);

  return {
    rows: state.rows,
    totalCount: state.totalCount,
    asOf: state.asOf,
    availability: state.availability,
    availabilityReason: state.availabilityReason,
    movementAvailable: state.movementAvailable,
    hasMore: state.nextCursor !== null,
    isLoading: status === "loading",
    isLoadingMore: status === "loadingMore",
    isReady: status === "ready",
    error,
    errorCode,
    errorSpecKey,
    loadMore,
    reload,
    retry,
  };
}
