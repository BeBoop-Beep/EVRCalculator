"use client";

import { useCallback } from "react";
import { getPokemonSetValueHistory } from "../../../lib/pokemon/pokemonSetMarketClient";
import { adaptSetValueTrend } from "../../../lib/pokemon/set-page/setPageAdapters.mjs";
import { pokemonSetPageQueryKeys } from "../../../lib/pokemon/set-page/queryKeys";
import { useSetPageQuery } from "./useSetPageQuery";

export function usePokemonSetValueTrendQuery(setId, options = {}) {
  const scope = options.scope || "standard";
  const days = options.days || 365;
  const enabled = options.enabled ?? Boolean(setId);
  const fetcher = useCallback(() => getPokemonSetValueHistory(setId, { days, scope }), [days, scope, setId]);
  return useSetPageQuery({
    queryKey: pokemonSetPageQueryKeys.setValueTrend(setId, { days, scope }),
    enabled,
    staleTime: options.staleTime ?? 5 * 60 * 1000,
    fetcher,
    adapter: adaptSetValueTrend,
  });
}
