"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getPokemonSetConsumerSealedSummary } from "@/lib/pokemon/pokemonSetMarketClient";
import { isRetryableSealedMarketError, isUnavailableSealedMarketError } from "./usePokemonSetSealedMarket";

export default function usePokemonSetSealedSummary(setId, { enabled = true } = {}) {
  const resolvedSetId = String(setId || "").trim();
  const lastGoodRef = useRef({ setId: null, payload: null });
  const [request, setRequest] = useState(() => ({ setId: enabled ? resolvedSetId : null, version: enabled && resolvedSetId ? 1 : 0 }));
  const [state, setState] = useState({ setId: resolvedSetId, status: "idle", payload: null, error: null, isRefreshing: false });
  const load = useCallback(() => setRequest((current) => ({ setId: resolvedSetId, version: current.version + 1 })), [resolvedSetId]);
  useEffect(() => {
    if (!enabled || !resolvedSetId) return;
    setRequest((current) => current.setId === resolvedSetId && current.version > 0
      ? current
      : { setId: resolvedSetId, version: current.version + 1 });
  }, [enabled, resolvedSetId]);
  useEffect(() => {
    if (!resolvedSetId || request.setId !== resolvedSetId || request.version === 0) {
      setState({ setId: resolvedSetId, status: "idle", payload: null, error: null, isRefreshing: false });
      return undefined;
    }
    let cancelled = false;
    const retained = lastGoodRef.current.setId === resolvedSetId ? lastGoodRef.current.payload : null;
    setState({ setId: resolvedSetId, status: "loading", payload: retained, error: null, isRefreshing: Boolean(retained) });
    const run = async (attempt = 0) => {
      try {
        const payload = await getPokemonSetConsumerSealedSummary(resolvedSetId);
        if (cancelled) return;
        lastGoodRef.current = { setId: resolvedSetId, payload };
        setState({ setId: resolvedSetId, status: "success", payload, error: null, isRefreshing: false });
      } catch (error) {
        if (cancelled) return;
        if (attempt === 0 && isRetryableSealedMarketError(error)) { setTimeout(() => { if (!cancelled) run(1); }, 300); return; }
        if (isUnavailableSealedMarketError(error)) setState({ setId: resolvedSetId, status: "unavailable", payload: null, error: null, isRefreshing: false });
        else setState({ setId: resolvedSetId, status: "error", payload: retained, error: "Unable to load Sealed market summary", isRefreshing: false });
      }
    };
    run();
    return () => { cancelled = true; };
  }, [request, resolvedSetId]);
  const identitySafeState = state.setId === resolvedSetId
    ? state
    : { setId: resolvedSetId, status: "idle", payload: null, error: null, isRefreshing: false };
  return { ...identitySafeState, load, retry: load };
}
