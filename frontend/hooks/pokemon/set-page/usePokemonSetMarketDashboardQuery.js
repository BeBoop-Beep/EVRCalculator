"use client";

import { useCallback } from "react";
import { getPokemonSetMarketDashboard } from "../../../lib/pokemon/pokemonSetMarketClient";
import { adaptSetValueTrend, adaptTopChaseCards } from "../../../lib/pokemon/set-page/setPageAdapters.mjs";
import { pokemonSetPageQueryKeys } from "../../../lib/pokemon/set-page/queryKeys";
import { useSetPageQuery } from "./useSetPageQuery";

export function usePokemonSetMarketDashboardQuery(setId, options = {}) {
  const window = options.window || "365d";
  const enabled = options.enabled ?? Boolean(setId);
  const fetcher = useCallback(() => getPokemonSetMarketDashboard(setId, { window }), [setId, window]);
  return useSetPageQuery({
    queryKey: pokemonSetPageQueryKeys.marketDashboard(setId, { window }),
    enabled,
    staleTime: options.staleTime ?? 6 * 60 * 60 * 1000,
    fetcher,
    adapter: (payload) => ({
      setValueTrend: adaptSetValueTrend(payload),
      topChaseCards: adaptTopChaseCards(payload),
      raw: payload,
    }),
  });
}
