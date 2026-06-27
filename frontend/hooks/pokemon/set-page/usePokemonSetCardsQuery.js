"use client";

import { useCallback } from "react";
import { getPokemonSetCards } from "../../../lib/pokemon/pokemonSetCardsClient";
import { adaptCards } from "../../../lib/pokemon/set-page/setPageAdapters.mjs";
import { pokemonSetPageQueryKeys } from "../../../lib/pokemon/set-page/queryKeys";
import { useSetPageQuery } from "./useSetPageQuery";

export function usePokemonSetCardsQuery(setId, options = {}) {
  const enabled = options.enabled ?? Boolean(setId);
  const fetcher = useCallback(() => getPokemonSetCards(setId), [setId]);
  return useSetPageQuery({
    queryKey: pokemonSetPageQueryKeys.cards(setId),
    enabled,
    staleTime: options.staleTime ?? 24 * 60 * 60 * 1000,
    fetcher,
    adapter: adaptCards,
  });
}
