"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getPokemonSetConsumerSealedSummary } from "@/lib/pokemon/pokemonSetMarketClient";
import { isRetryableSealedMarketError, isUnavailableSealedMarketError } from "./usePokemonSetSealedMarket";

export default function usePokemonSetSealedSummary(setId, { enabled = true } = {}) {
  const resolvedSetId = String(setId || "").trim();
  const lastGoodRef = useRef({ setId: null, payload: null });
  const [request, setRequest] = useState(() => ({ setId: enabled ? resolvedSetId : null, version: enabled ? 1 : 0 }));
  const [state, setState] = useState({ status: "idle", payload: null, error: null, isRefreshing: false });
  const load = useCallback(() => setRequest((current) => ({ setId: resolvedSetId, version: current.version + 1 })), [resolvedSetId]);
  useEffect(() => {
    if (!resolvedSetId || request.setId !== resolvedSetId || request.version === 0) return undefined;
    let cancelled = false;
    const retained = lastGoodRef.current.setId === resolvedSetId ? lastGoodRef.current.payload : null;
    setState({ status: "loading", payload: retained, error: null, isRefreshing: Boolean(retained) });
    const run = async (attempt = 0) => {
      try {
        const payload = await getPokemonSetConsumerSealedSummary(resolvedSetId);
        if (cancelled) return;
        lastGoodRef.current = { setId: resolvedSetId, payload };
        setState({ status: "success", payload, error: null, isRefreshing: false });
      } catch (error) {
        if (cancelled) return;
        if (attempt === 0 && isRetryableSealedMarketError(error)) { setTimeout(() => { if (!cancelled) run(1); }, 300); return; }
        if (isUnavailableSealedMarketError(error)) setState({ status: "unavailable", payload: null, error: null, isRefreshing: false });
        else setState({ status: "error", payload: retained, error: "Unable to load Sealed market summary", isRefreshing: false });
      }
    };
    run();
    return () => { cancelled = true; };
  }, [request, resolvedSetId]);
  return { ...state, load, retry: load };
}
