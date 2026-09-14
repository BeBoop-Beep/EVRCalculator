"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { buildQueryKey } from "@/lib/explore/marketExplorerQuery.mjs";
import { PREFLIGHT_STATE, preflightMessage, preflightRequestSpec, resolvePreflightState } from "@/lib/explore/marketExplorerPreflight.mjs";

export default function useMarketExplorerPreflight(spec, { enabled = true, debounceMs = 350 } = {}) {
  const requestSpec = useMemo(() => preflightRequestSpec(spec), [spec]);
  const identity = requestSpec ? buildQueryKey({ ...spec, mode: "all", topN: null }) : null;
  const generation = useRef(0);
  const [result, setResult] = useState({ state: PREFLIGHT_STATE.idle, payload: null, message: "", retryAfter: null });

  useEffect(() => {
    generation.current += 1;
    const requestGeneration = generation.current;
    const controller = new AbortController();
    if (!enabled || !requestSpec) {
      setResult({ state: PREFLIGHT_STATE.idle, payload: null, message: "", retryAfter: null });
      return () => controller.abort();
    }
    setResult({ state: PREFLIGHT_STATE.checking, payload: null, message: preflightMessage(PREFLIGHT_STATE.checking), retryAfter: null });
    const timer = setTimeout(async () => {
      try {
        const response = await fetch("/api/market/explorer/query/preflight", {
          method: "POST", credentials: "include", cache: "no-store", signal: controller.signal,
          headers: { "Content-Type": "application/json" }, body: JSON.stringify(requestSpec),
        });
        const payload = await response.json().catch(() => ({}));
        const retryAfter = response.headers.get("Retry-After") || payload?.retryAfterSeconds || null;
        const state = resolvePreflightState(payload, response.status);
        if (requestGeneration === generation.current && !controller.signal.aborted) {
          setResult({ state, payload, retryAfter, message: preflightMessage(state, payload, retryAfter) });
        }
      } catch (error) {
        if (error?.name !== "AbortError" && requestGeneration === generation.current) {
          setResult({ state: PREFLIGHT_STATE.failed, payload: null, retryAfter: null, message: preflightMessage(PREFLIGHT_STATE.failed) });
        }
      }
    }, debounceMs);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [enabled, identity]); // identity is canonical and order-insensitive

  return result;
}
