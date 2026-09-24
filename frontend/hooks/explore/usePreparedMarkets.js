"use client";

import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { createPreparedMarketLoader, loadedPreparedSeries } from "@/lib/explore/marketExplorerPreparedLoader.mjs";
import { fetchPreparedMarket } from "@/lib/explore/marketExplorerPrepared.mjs";

/**
 * React binding for the prepared-market lifecycle (see
 * marketExplorerPreparedLoader.mjs). `loadedKeys` is what is ACTUALLY on the
 * chart; `pendingKeys` and `failedKeys` are separate, so no consumer can mistake
 * "requested" for "active".
 */
export default function usePreparedMarkets({ fetchMarket = fetchPreparedMarket } = {}) {
  const [loader] = useState(() => createPreparedMarketLoader({ fetchMarket }));
  const snapshot = useSyncExternalStore(loader.subscribe, loader.getSnapshot, loader.getSnapshot);
  useEffect(() => () => loader.clear(), [loader]);
  return useMemo(() => ({
    loader,
    series: loadedPreparedSeries(snapshot),
    loadedKeys: snapshot.order.filter((key) => snapshot.loaded[key]),
    pendingKeys: snapshot.pending,
    failed: snapshot.failed,
    failedKeys: Object.keys(snapshot.failed),
  }), [loader, snapshot]);
}
