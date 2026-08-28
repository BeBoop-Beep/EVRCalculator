"use client";

import { useCallback, useEffect, useState } from "react";
import { getPokemonSetMarketSignals } from "@/lib/pokemon/pokemonSetMarketClient";

const RETRY_DELAY_MS = 350;
const RETRYABLE_STATUSES = new Set([502, 503, 504]);

export function isRetryableMarketSignalsError(error) {
  if (Number(error?.status) >= 400 && Number(error?.status) < 500) return false;
  return error?.retryable === true || error?.isTimeout === true || error?.name === "AbortError" ||
    RETRYABLE_STATUSES.has(Number(error?.status)) || (error instanceof TypeError && error?.status == null);
}

export default function usePokemonSetMarketSignals(setId, { enabled = false } = {}) {
  const resolvedSetId = String(setId || "").trim();
  const [requestVersion, setRequestVersion] = useState(0);
  const [state, setState] = useState({ status: "idle", payload: null, error: null, isRefreshing: false });
  const retry = useCallback(() => setRequestVersion((value) => value + 1), []);

  useEffect(() => {
    if (!enabled || !resolvedSetId) {
      setState({ status: "idle", payload: null, error: null, isRefreshing: false });
      return undefined;
    }
    let cancelled = false;
    let timer = null;
    setState({ status: "loading", payload: null, error: null, isRefreshing: false });
    const load = async (attempt = 0) => {
      try {
        const payload = await getPokemonSetMarketSignals(resolvedSetId);
        if (!cancelled) setState({ status: "success", payload, error: null, isRefreshing: false });
      } catch (error) {
        if (cancelled) return;
        if (attempt === 0 && isRetryableMarketSignalsError(error)) {
          timer = setTimeout(() => load(1), RETRY_DELAY_MS);
          return;
        }
        setState({
          status: error?.status === 403 ? "forbidden" : "error",
          payload: null,
          error: error?.status === 403 ? "Index Plus access could not be verified." : "Unable to load Market Breadth.",
          isRefreshing: false,
        });
      }
    };
    load();
    return () => { cancelled = true; if (timer !== null) clearTimeout(timer); };
  }, [enabled, requestVersion, resolvedSetId]);

  return { ...state, retry };
}
