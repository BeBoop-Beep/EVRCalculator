import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";
import { normalizePokemonCardDetail } from "@/lib/pokemon/pokemonCardDetailClient";
import { cache } from "react";

const DETAIL_REVALIDATE_SECONDS = 120;

export const getPokemonCardDetailServer = cache(async function getPokemonCardDetailServer(setId, cardId, variantId = null) {
  const url = new URL(
    `${getBackendApiBaseUrl()}/tcgs/pokemon/sets/${encodeURIComponent(setId)}/cards/${encodeURIComponent(cardId)}`
  );
  if (variantId) url.searchParams.set("variant_id", variantId);
  const response = await fetch(url.toString(), {
    headers: { Accept: "application/json" },
    next: {
      revalidate: DETAIL_REVALIDATE_SECONDS,
      tags: [`pokemon-card-detail:${String(setId)}:${String(cardId)}:${String(variantId || "canonical")}`],
    },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(payload?.message || "Unable to load Pokemon card detail");
    error.status = response.status;
    error.code = payload?.code;
    throw error;
  }
  return normalizePokemonCardDetail(payload);
});
