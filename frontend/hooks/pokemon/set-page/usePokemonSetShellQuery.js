"use client";

import { useCallback } from "react";
import { adaptSetShell } from "../../../lib/pokemon/set-page/setPageAdapters.mjs";
import { pokemonSetPageQueryKeys } from "../../../lib/pokemon/set-page/queryKeys";
import { useSetPageQuery } from "./useSetPageQuery";

async function fetchSetPagePayload(setId) {
  const response = await fetch(`/api/tcgs/pokemon/sets/${encodeURIComponent(setId)}/page`, {
    method: "GET",
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.message || payload?.error || "Unable to load Pokemon set page shell");
  }
  return payload;
}

export function usePokemonSetShellQuery(setId, options = {}) {
  const enabled = options.enabled ?? Boolean(setId);
  const fetcher = useCallback(() => fetchSetPagePayload(setId), [setId]);
  return useSetPageQuery({
    queryKey: pokemonSetPageQueryKeys.shell(setId),
    enabled,
    staleTime: options.staleTime ?? 5 * 60 * 1000,
    fetcher,
    adapter: adaptSetShell,
    initialData: options.initialData ? adaptSetShell(options.initialData) : null,
  });
}
