"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import SetMarketMobile from "@/components/pokemon/set-page/Market/SetMarketMobile";
import {
  getPokemonSetMarketMovers,
  getPokemonSetOverview,
  getPokemonSetTopChase,
  getPokemonSetValueHistory,
  getPokemonSetConsumerSealedMarket,
} from "@/lib/pokemon/pokemonSetMarketClient";
import { createMarketModuleState, marketSeedMatchesSet, readLatestSetValue, selectMarketAsOfDate } from "./marketRuntimeState.mjs";

const MARKET_WINDOW = "365d";
const MOVERS_WINDOW = "7D";
const successfulMarketState = new Map();

function remember(setId, patch) {
  successfulMarketState.set(setId, { ...(successfulMarketState.get(setId) || {}), ...patch });
  while (successfulMarketState.size > 10) successfulMarketState.delete(successfulMarketState.keys().next().value);
}

function cardsHref(setSlug, section) {
  return `/TCGs/Pokemon/Sets/${encodeURIComponent(setSlug || "")}?tab=cards&section=${section}`;
}

export default function MarketSetTab({ setId, setSlug, overviewSeed = null, moversSeed = null }) {
  const validOverviewSeed = marketSeedMatchesSet(overviewSeed, setId) ? overviewSeed : null;
  const validMoversSeed = marketSeedMatchesSet(moversSeed, setId) ? moversSeed : null;
  const cached = successfulMarketState.get(setId) || {};
  const [overview, setOverview] = useState(() => createMarketModuleState(setId, validOverviewSeed || cached.overview || null));
  const [movers, setMovers] = useState(() => createMarketModuleState(setId, validMoversSeed || cached.movers || null));
  const [topChase, setTopChase] = useState(() => createMarketModuleState(setId, validOverviewSeed?.topChaseCards?.length ? { ...validOverviewSeed, cards: validOverviewSeed.topChaseCards } : cached.topChase || null));
  const [topWindow, setTopWindow] = useState("7D");
  const [retry, setRetry] = useState({ overview: 0, movers: 0, topChase: 0 });
  const activeSetRef = useRef(setId);
  activeSetRef.current = setId;

  useEffect(() => {
    if (!setId || (overview.setId === setId && overview.payload)) return;
    let cancelled = false;
    setOverview(createMarketModuleState(setId));
    setOverview((state) => ({ ...state, status: "loading" }));
    getPokemonSetOverview(setId, { window: MARKET_WINDOW }).then((payload) => {
      if (cancelled || activeSetRef.current !== setId) return;
      remember(setId, { overview: payload });
      setOverview({ status: "success", setId, payload, error: null });
    }).catch((error) => {
      if (!cancelled && activeSetRef.current === setId) setOverview({ status: "error", setId, payload: null, error: error?.message || "Unable to load Market overview." });
    });
    return () => { cancelled = true; };
  }, [setId, retry.overview]);

  useEffect(() => {
    if (!setId || (movers.setId === setId && movers.payload)) return;
    let cancelled = false;
    setMovers({ ...createMarketModuleState(setId), status: "loading" });
    getPokemonSetMarketMovers(setId, { window: MOVERS_WINDOW, limit: 10, surface: "set-page", metric: "absolute-percent" }).then((payload) => {
      if (cancelled || activeSetRef.current !== setId) return;
      remember(setId, { movers: payload });
      setMovers({ status: "success", setId, payload, error: null });
    }).catch((error) => {
      if (!cancelled && activeSetRef.current === setId) setMovers({ status: "error", setId, payload: null, error: error?.message || "Unable to load Market movers." });
    });
    return () => { cancelled = true; };
  }, [setId, retry.movers]);

  // The compact bootstrap preview paints immediately. Detailed per-card
  // histories start progressively after overview is usable, never on the
  // server route's critical path.
  useEffect(() => {
    if (!setId || !overview.payload) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      setTopChase((state) => ({ ...state, status: state.payload ? "refreshing" : "loading", setId }));
      getPokemonSetTopChase(setId, { window: MARKET_WINDOW, limit: 10 }).then((payload) => {
        if (cancelled || activeSetRef.current !== setId) return;
        remember(setId, { topChase: payload });
        setTopChase({ status: "success", setId, payload, error: null });
      }).catch((error) => {
        if (!cancelled && activeSetRef.current === setId) setTopChase((state) => ({ ...state, status: "error", error: error?.message || "Unable to load Top Chase histories." }));
      });
    }, 0);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [setId, overview.payload, retry.topChase]);

  // Keep the endpoint ownership explicit in this tab. Scope history and full
  // sealed data remain user/progressive paths; they are not invoked by first
  // render. SetMarketMobile owns the existing sealed summary/full-market UI.
  const loadScopeHistory = useCallback((scope) => getPokemonSetValueHistory(setId, { days: 365, scope }), [setId]);
  const warmSealedMarket = useCallback(() => {
    if (typeof navigator !== "undefined" && navigator.connection?.saveData === true) return Promise.resolve(null);
    return getPokemonSetConsumerSealedMarket(setId);
  }, [setId]);

  useEffect(() => {
    const scopes = overview.payload?.setValueHistoriesByScope || {};
    if (!setId || !overview.payload || Array.isArray(scopes.top10)) return;
    let cancelled = false;
    loadScopeHistory("top10").then((payload) => {
      if (cancelled || activeSetRef.current !== setId) return;
      setOverview((state) => ({
        ...state,
        payload: {
          ...state.payload,
          setValueHistoriesByScope: { ...(state.payload?.setValueHistoriesByScope || {}), top10: payload?.history || [] },
        },
      }));
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [setId, overview.payload, loadScopeHistory]);

  useEffect(() => {
    if (!setId || !overview.payload || typeof window === "undefined") return;
    const run = () => { warmSealedMarket().catch(() => {}); };
    if (typeof window.requestIdleCallback === "function") {
      const id = window.requestIdleCallback(run, { timeout: 2500 });
      return () => window.cancelIdleCallback?.(id);
    }
    const id = window.setTimeout(run, 1500);
    return () => window.clearTimeout(id);
  }, [setId, overview.payload, warmSealedMarket]);

  const activeOverview = overview.setId === setId ? overview : createMarketModuleState(setId);
  const activeMovers = movers.setId === setId ? movers : createMarketModuleState(setId);
  const activeTopChase = topChase.setId === setId ? topChase : createMarketModuleState(setId);
  const overviewPayload = activeOverview.payload || {};
  const histories = overviewPayload.setValueHistoriesByScope || {};
  const standardHistory = histories.standard || [];
  const top10History = histories.top10 || [];
  const topCards = activeTopChase.payload?.cards || activeTopChase.payload?.topChaseCards || overviewPayload.topChaseCards || [];
  const marketAsOfDate = selectMarketAsOfDate(activeTopChase.payload, activeMovers.payload, overviewPayload);
  const cardsMarket = overviewPayload.cardsMarket || null;
  const cardsTrackedCount = cardsMarket?.trackedItems ?? cardsMarket?.tracked_items ?? cardsMarket?.trackedCount ?? null;
  const moversEntry = activeMovers.payload ? { ...activeMovers.payload, all: activeMovers.payload.all || [] } : null;

  return (
    <SetMarketMobile
      setId={setId}
      setSlug={setSlug}
      sectionIds={{ root: "set-detail-market", movers: "set-detail-market-movers", setValue: "set-detail-market-set-value", topChase: "set-detail-market-top-chase", sealed: "set-detail-market-sealed" }}
      movers={{ entry: moversEntry, status: activeMovers.status, error: activeMovers.error, viewAllHref: cardsHref(setSlug, "market-movers"), onRetry: () => setRetry((value) => ({ ...value, movers: value.movers + 1 })) }}
      setValue={{ history: standardHistory, historiesByScope: histories, status: activeOverview.status, error: activeOverview.error, cardsTrackedCount, top10Value: readLatestSetValue(top10History), standardValue: readLatestSetValue(standardHistory), moversByWindow: activeMovers.payload ? { [MOVERS_WINDOW]: activeMovers.payload } : null, cardsMarket }}
      topChase={{ cards: topCards, status: activeTopChase.payload ? "success" : activeTopChase.status, error: activeTopChase.error, selectedWindowKey: topWindow, onWindowChange: setTopWindow, marketAsOfDate, viewAllHref: cardsHref(setSlug, "all-cards"), onRetry: () => setRetry((value) => ({ ...value, topChase: value.topChase + 1 })) }}
    />
  );
}
