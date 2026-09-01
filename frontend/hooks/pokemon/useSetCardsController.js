"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { buildCardsRequestKey, buildCardsScopeKey } from "@/components/pokemon/set-page/tabs/cardsRequestKey.mjs";
import { PRICING_SNAPSHOT_CONTRACT_VERSION } from "@/lib/pokemon/pricingSnapshotContract.mjs";
import { markSectionTiming, debugSectionTiming } from "@/lib/perf/sectionTiming";
import { createCardsPageState, mergeCardsPage } from "./setCardsControllerState.mjs";

const getCardsClient = () => import("@/lib/pokemon/pokemonSetCardsClient");
const getCardsPage = (...args) => getCardsClient().then((client) => client.getPokemonSetCardsPage(...args));
const prefetchCardsPage = (...args) => getCardsClient().then((client) => client.prefetchPokemonSetCardsPage(...args));

export default function useSetCardsController({
  enabled,
  canFetch,
  setId,
  section,
  sort,
  sortDirection,
  query,
  rarity,
  movementFilter,
  movementSort,
  movementMetric,
  pageSize = 60,
  pricingContractVersion = PRICING_SNAPSHOT_CONTRACT_VERSION,
}) {
  const [page, setPage] = useState(1);
  const [state, setState] = useState(() => createCardsPageState(setId));
  const [retryNonce, setRetryNonce] = useState(0);
  const lastRequestKeyRef = useRef(null);
  const activeRequestKeyRef = useRef(null);
  const activeSetIdRef = useRef(setId);
  const stateScopeKeyRef = useRef(state.scopeKey);
  activeSetIdRef.current = setId;
  stateScopeKeyRef.current = state.scopeKey;

  const request = useMemo(() => ({
    setId,
    pricingContractVersion,
    section,
    sort,
    sortDirection,
    query: String(query || "").trim() || null,
    rarity: rarity || null,
    movementFilter,
    movementSort,
    movementMetric: movementMetric || null,
    page,
    pageSize,
  }), [setId, pricingContractVersion, section, sort, sortDirection, query, rarity, movementFilter, movementSort, movementMetric, page, pageSize]);
  const scopeKey = useMemo(() => buildCardsScopeKey(request), [request]);
  const requestKey = useMemo(() => buildCardsRequestKey(request), [request]);
  const activeState = state.setId === setId ? state : createCardsPageState(setId);

  useEffect(() => setPage(1), [scopeKey]);

  useEffect(() => {
    if (!setId) {
      setState(createCardsPageState());
      return undefined;
    }
    if (!canFetch) {
      setState((previous) => ({
        status: previous.setId === setId && previous.cards.length > 0 ? previous.status : "empty",
        setId,
        scopeKey: previous.setId === setId ? previous.scopeKey : null,
        page,
        cards: previous.setId === setId ? previous.cards : [],
        pagination: previous.setId === setId ? previous.pagination : null,
        filters: previous.setId === setId ? previous.filters : null,
        meta: previous.setId === setId ? previous.meta : null,
        error: null,
      }));
      return undefined;
    }
    if (!enabled) return undefined;
    if (page > 1 && stateScopeKeyRef.current !== scopeKey) return undefined;
    if (lastRequestKeyRef.current === requestKey) return undefined;

    lastRequestKeyRef.current = requestKey;
    activeRequestKeyRef.current = requestKey;
    let cancelled = false;
    let settled = false;
    setState((previous) => {
      const sameScope = previous.setId === setId && previous.scopeKey === scopeKey;
      if (page > 1 && sameScope && previous.cards.length > 0) {
        return { ...previous, status: "loading_more", error: null };
      }
      return { ...createCardsPageState(setId), status: "loading", scopeKey, page };
    });
    const startedAt = typeof performance !== "undefined" ? performance.now() : Date.now();
    getCardsPage(setId, {
      page,
      pageSize,
      sort,
      sortDirection,
      query: request.query,
      rarity,
      movementFilter,
      movementSort,
      movementMetric,
      section,
    }).then((payload) => {
      settled = true;
      if (cancelled || activeSetIdRef.current !== setId || activeRequestKeyRef.current !== requestKey) return;
      setState((previous) => activeRequestKeyRef.current === requestKey
        ? mergeCardsPage(previous, payload, { setId, scopeKey, requestedPage: page })
        : previous);
      const elapsedMs = Math.round((typeof performance !== "undefined" ? performance.now() : Date.now()) - startedAt);
      const metric = page > 1 ? "cardsNextBatch" : "cardsFirstBatch";
      markSectionTiming(`${metric}_success`, { setId, tab: "cards", page, elapsedMs });
      debugSectionTiming("[section-timing]", `${metric}Ms`, { setId, tab: "cards", page, elapsedMs });
    }).catch((error) => {
      settled = true;
      if (lastRequestKeyRef.current === requestKey) lastRequestKeyRef.current = null;
      if (cancelled || activeSetIdRef.current !== setId || activeRequestKeyRef.current !== requestKey) return;
      setState((previous) => ({
        status: previous.setId === setId && previous.cards.length > 0 ? "success_stale" : "error",
        setId,
        scopeKey: previous.setId === setId ? previous.scopeKey : null,
        page,
        cards: previous.setId === setId ? previous.cards : [],
        pagination: previous.setId === setId ? previous.pagination : null,
        filters: previous.setId === setId ? previous.filters : null,
        meta: previous.setId === setId ? previous.meta : null,
        error: error?.message || "Unable to load cards for this set.",
      }));
    });
    return () => {
      cancelled = true;
      if (!settled && lastRequestKeyRef.current === requestKey) lastRequestKeyRef.current = null;
    };
  }, [canFetch, enabled, page, pageSize, request.query, requestKey, retryNonce, scopeKey, section, setId, sort, sortDirection, rarity, movementFilter, movementSort, movementMetric]);

  const retry = useCallback(() => {
    lastRequestKeyRef.current = null;
    setRetryNonce((value) => value + 1);
  }, []);
  const prefetchPageOne = useCallback(() => prefetchCardsPage(setId, {
    page: 1, pageSize, sort, sortDirection, query: request.query, rarity,
    movementFilter, movementSort, movementMetric, section,
  }), [setId, pageSize, sort, sortDirection, request.query, rarity, movementFilter, movementSort, movementMetric, section]);

  return { state: activeState, page, setPage, scopeKey, retry, prefetchPageOne };
}
