"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { queryKeyToString } from "../../../lib/pokemon/set-page/queryKeys";

export function useSetPageQuery({
  queryKey,
  enabled = true,
  staleTime = 5 * 60 * 1000,
  fetcher,
  adapter = (payload) => payload,
  initialData = null,
}) {
  const cacheRef = useRef(new Map());
  const cacheKey = useMemo(() => queryKeyToString(queryKey), [queryKey]);
  const [state, setState] = useState(() => ({
    status: initialData ? "success" : "idle",
    data: initialData,
    error: null,
  }));

  useEffect(() => {
    if (!enabled || !cacheKey || typeof fetcher !== "function") {
      return undefined;
    }

    const cached = cacheRef.current.get(cacheKey);
    if (cached && Date.now() - cached.cachedAt <= staleTime) {
      setState({ status: "success", data: cached.data, error: null });
      return undefined;
    }

    const controller = new AbortController();
    setState((previous) => ({
      status: previous.data ? "success" : "loading",
      data: previous.data,
      error: null,
    }));

    Promise.resolve()
      .then(() => fetcher({ signal: controller.signal }))
      .then((payload) => {
        if (controller.signal.aborted) {
          return;
        }
        const data = adapter(payload);
        cacheRef.current.set(cacheKey, { data, cachedAt: Date.now() });
        setState({ status: "success", data, error: null });
      })
      .catch((error) => {
        if (controller.signal.aborted) {
          return;
        }
        setState((previous) => ({
          status: "error",
          data: previous.data,
          error,
        }));
      });

    return () => controller.abort();
  }, [adapter, cacheKey, enabled, fetcher, staleTime]);

  return state;
}
