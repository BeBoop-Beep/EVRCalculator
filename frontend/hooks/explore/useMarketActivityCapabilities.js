"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { fetchMarketActivityCapabilities } from "@/lib/explore/marketActivityApi.mjs";
import {
  activityCapabilityBatchKey,
  eligibleActivityMarkets,
  normalizeCapabilityResponse,
} from "@/lib/explore/marketActivityCapabilities.mjs";

const cache = new Map();

export function clearMarketActivityCapabilityCache() {
  cache.clear();
}

export default function useMarketActivityCapabilities({
  activeSeries,
  identityKey,
  plan,
  enabled = true,
  transport = fetchMarketActivityCapabilities,
}) {
  const markets = useMemo(
    () => eligibleActivityMarkets(activeSeries),
    [activeSeries],
  );
  const batchKey = activityCapabilityBatchKey(markets, identityKey, plan);
  const [state, setState] = useState({
    status: "idle",
    capabilities: {},
    error: null,
  });
  const sequence = useRef(0);
  const lifecycle = useRef({ identityKey, plan });

  useEffect(() => {
    const previous = lifecycle.current;
    lifecycle.current = { identityKey, plan };
    const rank = { basic: 1, plus: 2, premium: 3 };
    if (
      !identityKey ||
      previous.identityKey !== identityKey ||
      (rank[plan] || 1) < (rank[previous.plan] || 1)
    )
      cache.clear();
  }, [identityKey, plan]);

  useEffect(() => {
    const requestSequence = ++sequence.current;
    if (!enabled || !batchKey) {
      setState({ status: "idle", capabilities: {}, error: null });
      return undefined;
    }
    if (cache.has(batchKey)) {
      setState({
        status: "ready",
        capabilities: cache.get(batchKey),
        error: null,
      });
      return undefined;
    }
    const controller = new AbortController();
    setState({ status: "loading", capabilities: {}, error: null });
    transport({ markets, windowDays: 30, signal: controller.signal })
      .then((payload) => {
        if (controller.signal.aborted || requestSequence !== sequence.current)
          return;
        const capabilities = normalizeCapabilityResponse(payload, markets);
        cache.set(batchKey, capabilities);
        setState({ status: "ready", capabilities, error: null });
      })
      .catch((error) => {
        if (
          controller.signal.aborted ||
          requestSequence !== sequence.current ||
          error?.name === "AbortError"
        )
          return;
        setState({ status: "error", capabilities: {}, error });
      });
    return () => controller.abort();
  }, [batchKey, enabled, markets, transport]);

  return state;
}
