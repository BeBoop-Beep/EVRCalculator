"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchAssetOptions } from "@/lib/explore/marketExplorerAssetOptions.mjs";

/**
 * Truthful per-asset option states (rarity taxonomy / sealed types) from the
 * backend. `status`: idle | loading | ready | unavailable. Unavailable is a
 * legacy-mode signal: callers fall back to their existing behavior.
 */
export default function useAssetOptions(asset, { enabled = true, fetcher = fetchAssetOptions } = {}) {
  const [state, setState] = useState({ status: "idle", data: null });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!enabled || !asset) return undefined;
    const controller = new AbortController();
    setState((current) => ({ status: "loading", data: current.data }));
    fetcher(asset, { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) setState({ status: "ready", data }); })
      .catch((error) => { if (error?.name !== "AbortError" && !controller.signal.aborted) setState({ status: "unavailable", data: null }); });
    return () => controller.abort();
  }, [asset, enabled, fetcher, attempt]);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return { ...state, retry };
}
