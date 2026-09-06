"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  appendConstituentPage,
  fetchConstituentPage,
  CONSTITUENT_PAGE_DEFAULT_LIMIT,
} from "@/lib/explore/marketExplorerConstituentPaging.mjs";

const IDLE = { rows: [], totalCount: 0, nextCursor: null, asOf: null };

/**
 * Incrementally loaded constituents for ONE query-built market, keyed by its
 * spec (== its identity — see marketExplorerQuery.mjs).
 *
 * DELIBERATELY SEPARATE FROM THE MARKET-SUMMARY FETCH. Building a market (or
 * toggling which chart series is visible) never touches this hook; it only
 * runs when the Constituents section is actually inspecting a query-built
 * market, and its own loading/error state never blocks the chart, the
 * legend or Active Markets from being interactive. A user can watch the
 * chart update while a Global-scale constituent page is still loading.
 *
 * NEVER HOLDS THE WHOLE ROSTER AT ONCE UNLESS THE USER ASKS FOR IT PAGE BY
 * PAGE. Each `loadMore()` call appends one backend page (<=100 rows); nothing
 * here ever requests or assumes a complete in-memory copy of a 33,955-row
 * market.
 */
export default function useMarketExplorerConstituentPage(spec, { limit = CONSTITUENT_PAGE_DEFAULT_LIMIT, autoLoad = true } = {}) {
  const [state, setState] = useState(IDLE);
  const [status, setStatus] = useState("idle"); // idle | loading | loadingMore | ready | error
  const [error, setError] = useState(null);
  // Guards a page response arriving after the inspected market changed.
  const requestSpecRef = useRef(null);

  const specKey = spec ? JSON.stringify(spec) : null;

  const load = useCallback(async (afterRank, { appending }) => {
    if (!spec) return;
    requestSpecRef.current = specKey;
    setStatus(appending ? "loadingMore" : "loading");
    setError(null);
    try {
      const page = await fetchConstituentPage(spec, { limit, afterRank });
      // The inspected market moved on while this page was in flight; drop it
      // rather than mixing two markets' rows in one table.
      if (requestSpecRef.current !== specKey) return;
      setState((current) => ({
        rows: appending ? appendConstituentPage(current.rows, page) : page.rows,
        totalCount: page.totalCount,
        nextCursor: page.nextCursor,
        asOf: page.asOf,
      }));
      setStatus("ready");
    } catch (exc) {
      if (requestSpecRef.current !== specKey) return;
      setError(exc instanceof Error ? exc.message : "Unable to load constituents");
      setStatus("error");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [specKey, limit]);

  useEffect(() => {
    setState(IDLE);
    setError(null);
    setStatus(spec ? "idle" : "idle");
    if (spec && autoLoad) load(0, { appending: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [specKey, autoLoad]);

  const loadMore = useCallback(() => {
    if (state.nextCursor === null || status === "loading" || status === "loadingMore") return;
    load(state.nextCursor, { appending: true });
  }, [load, state.nextCursor, status]);

  const reload = useCallback(() => load(0, { appending: false }), [load]);

  return {
    rows: state.rows,
    totalCount: state.totalCount,
    asOf: state.asOf,
    hasMore: state.nextCursor !== null,
    isLoading: status === "loading",
    isLoadingMore: status === "loadingMore",
    isReady: status === "ready",
    error,
    loadMore,
    reload,
  };
}
