function text(value) {
  const normalized = value == null ? "" : String(value).trim();
  return normalized || null;
}

export function buildPokemonCardHref(setSlug, card, variantId = undefined) {
  const slug = text(setSlug);
  const canonicalId = text(card?.canonicalCardId || card?.canonical_card_id || card?.id);
  if (!slug || !canonicalId) return null;
  const selectedVariant = text(
    variantId === undefined ? (card?.cardVariantId || card?.card_variant_id) : variantId
  );
  const base = `/TCGs/Pokemon/Sets/${encodeURIComponent(slug)}/Cards/${encodeURIComponent(canonicalId)}`;
  return selectedVariant ? `${base}?variant=${encodeURIComponent(selectedVariant)}` : base;
}

export function normalizePokemonCardDetail(payload) {
  if (!payload || typeof payload !== "object") return null;
  return {
    set: payload.set || {},
    card: payload.card || {},
    availableVariants: Array.isArray(payload.availableVariants) ? payload.availableVariants : [],
    selectedVariantId: text(payload.selectedVariantId),
    variantSelection: payload.variantSelection || { state: "unavailable", source: null },
    market: payload.market || {},
    chase: payload.chase || { available: false, reason: "modeled_chase_unavailable" },
    intelligence: payload.intelligence || { available: false, reason: "card_intelligence_unavailable" },
    meta: payload.meta || {},
  };
}

export async function getPokemonCardDetail(setId, cardId, variantId, { signal } = {}) {
  const resolvedSet = text(setId);
  const resolvedCard = text(cardId);
  if (!resolvedSet || !resolvedCard) throw new Error("Set and canonical card ids are required");
  const url = new URL(
    `/api/tcgs/pokemon/sets/${encodeURIComponent(resolvedSet)}/cards/${encodeURIComponent(resolvedCard)}`,
    window.location.origin
  );
  if (text(variantId)) url.searchParams.set("variant_id", text(variantId));
  const response = await fetch(url.toString(), { method: "GET", cache: "no-store", signal });
  let payload = null;
  try { payload = await response.json(); } catch { payload = null; }
  if (!response.ok) {
    const error = new Error(payload?.message || "Unable to load Pokemon card detail");
    error.status = response.status;
    error.code = payload?.code;
    throw error;
  }
  return normalizePokemonCardDetail(payload);
}
