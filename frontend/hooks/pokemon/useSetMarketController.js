"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import {
  getPokemonSetMarketMovers,
  getPokemonSetOverview,
  getPokemonSetTopChase,
  getPokemonSetValueHistory,
} from "@/lib/pokemon/pokemonSetMarketClient";
import {
  createMarketDashboardState,
  marketDashboardReducer,
} from "@/components/explore/marketDashboardState.mjs";

const OVERVIEW_WINDOW = "365d";
const TOP_CHASE_WINDOW = "365d";
const MOVERS_WINDOW = "7D";
const MOVERS_LIMIT = 10;
const activeForSet = (state, setId, sourceWindow) => state.setId === setId
  ? state
  : createMarketDashboardState({ status: "idle", setId, sourceWindow });

function useMarketResource({ setId, enabled, canFetch, seed, seedSatisfies = Boolean(seed), sourceWindow, request, errorMessage }) {
  const [state, dispatch] = useReducer(marketDashboardReducer, {
    status: seed ? "success" : "idle", setId, payload: seed || null, sourceWindow,
  }, createMarketDashboardState);
  const [retryNonce, setRetryNonce] = useState(0);
  const lastRequestKeyRef = useRef(null);
  const activeRequestKeyRef = useRef(null);
  const activeSetIdRef = useRef(setId);
  const activeStatusRef = useRef("idle");
  activeSetIdRef.current = setId;
  const activeState = activeForSet(state, setId, sourceWindow);
  activeStatusRef.current = activeState.status;

  useEffect(() => {
    if (!seed || !setId || retryNonce > 0) return;
    // A compact bootstrap preview is useful while the dedicated resource is
    // loading, but it must not claim the request key. Otherwise the fetch
    // effect below sees a successful seeded state and mistakes the preview for
    // the completed history-bearing resource.
    if (seedSatisfies) {
      lastRequestKeyRef.current = `${setId}|${sourceWindow}`;
    }
    dispatch({ type: "success", setId, payload: seed, sourceWindow });
  }, [retryNonce, seed, seedSatisfies, setId, sourceWindow]);

  useEffect(() => {
    if (!setId || !canFetch) {
      dispatch({ type: "reset", status: "empty", setId: setId || null, sourceWindow });
      return undefined;
    }
    if (!enabled || (seedSatisfies && retryNonce === 0)) return undefined;
    const requestKey = `${setId}|${sourceWindow}`;
    if (lastRequestKeyRef.current === requestKey && ["loading", "success", "success_stale"].includes(activeStatusRef.current)) return undefined;
    lastRequestKeyRef.current = requestKey;
    activeRequestKeyRef.current = requestKey;
    let cancelled = false;
    let settled = false;
    dispatch({ type: "loading", setId, sourceWindow });
    request(setId).then((payload) => {
      settled = true;
      if (cancelled || activeSetIdRef.current !== setId || activeRequestKeyRef.current !== requestKey) return;
      dispatch({ type: "success", setId, payload, sourceWindow });
    }).catch((error) => {
      settled = true;
      if (lastRequestKeyRef.current === requestKey) lastRequestKeyRef.current = null;
      if (cancelled || activeSetIdRef.current !== setId || activeRequestKeyRef.current !== requestKey) return;
      dispatch({ type: "error", setId, error: error?.message || errorMessage, sourceWindow });
    });
    return () => {
      cancelled = true;
      if (!settled && lastRequestKeyRef.current === requestKey) lastRequestKeyRef.current = null;
    };
  }, [canFetch, enabled, errorMessage, request, retryNonce, seedSatisfies, setId, sourceWindow]);

  const retry = useCallback(() => {
    lastRequestKeyRef.current = null;
    setRetryNonce((value) => value + 1);
  }, []);
  return { state, activeState, retry };
}

export default function useSetMarketController({
  setId,
  enabled,
  canFetch,
  destinationSeedPending,
  overviewSeed,
  moversSeed,
  topChaseSeed,
}) {
  const overviewRequest = useCallback((id) => getPokemonSetOverview(id, { window: OVERVIEW_WINDOW }), []);
  const moversRequest = useCallback((id) => getPokemonSetMarketMovers(id, {
    window: MOVERS_WINDOW, limit: MOVERS_LIMIT, surface: "set-page", metric: "absolute-percent",
  }), []);
  const topChaseRequest = useCallback((id) => getPokemonSetTopChase(id, { window: TOP_CHASE_WINDOW, limit: 10 }), []);
  const overview = useMarketResource({
    setId, enabled: enabled && !destinationSeedPending, canFetch, seed: overviewSeed,
    sourceWindow: OVERVIEW_WINDOW, request: overviewRequest, errorMessage: "Unable to load set overview for this set.",
  });
  const movers = useMarketResource({
    setId, enabled: enabled && !destinationSeedPending, canFetch, seed: moversSeed,
    sourceWindow: MOVERS_WINDOW, request: moversRequest, errorMessage: "Unable to load market movers for this set.",
  });
  const criticalSettled = [overview.activeState.status, movers.activeState.status]
    .every((status) => ["success", "success_stale", "error", "empty"].includes(status));
  const topChase = useMarketResource({
    setId,
    enabled: enabled && criticalSettled,
    canFetch,
    seed: topChaseSeed,
    seedSatisfies: Boolean(topChaseSeed) && topChaseSeed?.meta?.topChasePreviewOnly !== true,
    sourceWindow: TOP_CHASE_WINDOW,
    request: topChaseRequest,
    errorMessage: "Unable to load top chase cards for this set.",
  });
  return {
    overviewState: overview.state,
    activeOverviewState: overview.activeState,
    marketMoversState: movers.state,
    activeMarketMoversState: movers.activeState,
    topChaseState: topChase.state,
    activeTopChaseState: topChase.activeState,
    retryOverview: overview.retry,
    retryMarketMovers: movers.retry,
    retryTopChase: topChase.retry,
  };
}
