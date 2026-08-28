"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getPokemonSetSealedMarket } from "@/lib/pokemon/pokemonSetMarketClient";

const RETRY_DELAY_MS = 300;
const RETRYABLE_STATUS_CODES = new Set([502, 503, 504]);
const NON_RETRYABLE_CONTRACT_CODES = new Set([
  "POKEMON_SET_SEALED_MARKET_IDENTITY_MISMATCH",
]);

export function isRetryableSealedMarketError(error) {
  if (NON_RETRYABLE_CONTRACT_CODES.has(error?.code)) return false;
  if (error?.retryable === true || error?.isTimeout === true) return true;
  if (RETRYABLE_STATUS_CODES.has(Number(error?.status))) return true;
  return error instanceof TypeError && error?.status == null;
}

export function isUnavailableSealedMarketError(error) {
  return Number(error?.status) === 404;
}

export default function usePokemonSetSealedMarket(setId, { enabled = true } = {}) {
  const resolvedSetId = String(setId || "").trim();
  const lastGoodRef = useRef({ setId: null, payload: null });
  const [requestVersion, setRequestVersion] = useState(enabled ? 1 : 0);
  const [state, setState] = useState({
    status: "idle",
    payload: null,
    error: null,
    isRefreshing: false,
  });

  const load = useCallback(() => setRequestVersion((version) => version + 1), []);
  const retry = load;

  useEffect(() => {
    if (!resolvedSetId || requestVersion === 0) {
      lastGoodRef.current = { setId: null, payload: null };
      setState({ status: "idle", payload: null, error: null, isRefreshing: false });
      return undefined;
    }

    let cancelled = false;
    let retryTimer = null;
    const retainedPayload = lastGoodRef.current.setId === resolvedSetId ? lastGoodRef.current.payload : null;
    setState({
      status: "loading",
      payload: retainedPayload,
      error: null,
      isRefreshing: retainedPayload !== null,
    });

    const load = async (attempt = 0) => {
      try {
        const payload = await getPokemonSetSealedMarket(resolvedSetId);
        if (cancelled) return;
        lastGoodRef.current = { setId: resolvedSetId, payload };
        setState({ status: "success", payload, error: null, isRefreshing: false });
      } catch (error) {
        if (cancelled) return;
        if (attempt === 0 && isRetryableSealedMarketError(error)) {
          retryTimer = setTimeout(() => load(1), RETRY_DELAY_MS);
          return;
        }
        const payload = lastGoodRef.current.setId === resolvedSetId ? lastGoodRef.current.payload : null;
        if (isUnavailableSealedMarketError(error)) {
          setState({ status: "unavailable", payload: null, error: null, isRefreshing: false });
          return;
        }
        setState({
          status: "error",
          payload,
          error: "Unable to load Sealed market",
          isRefreshing: false,
        });
      }
    };

    load();
    return () => {
      cancelled = true;
      if (retryTimer !== null) clearTimeout(retryTimer);
    };
  }, [requestVersion, resolvedSetId]);

  return { ...state, retry, load };
}
