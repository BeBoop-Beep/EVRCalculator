import { toSetSlug } from "@/utils/slugify";

function text(value) {
  const normalized = value == null ? "" : String(value).trim();
  return normalized || null;
}

export function buildPokemonCardDetailHref(input = {}) {
  const card = input?.card || input;
  const slug = toSetSlug(text(
    input?.setSlug || input?.setCanonicalKey || input?.set_canonical_key ||
    input?.canonicalKey || input?.canonical_key || card?.setCanonicalKey ||
    card?.set_canonical_key || card?.canonicalKey || card?.canonical_key ||
    input?.setId || input?.set_id || card?.setId || card?.set_id
  ));
  const canonicalId = text(
    input?.canonicalCardId || input?.canonical_card_id || card?.canonicalCardId ||
    card?.canonical_card_id || input?.cardId || input?.card_id || card?.cardId || card?.card_id
  );
  if (!slug || !canonicalId) return null;
  const selectedVariant = text(
    input?.cardVariantId || input?.card_variant_id || card?.cardVariantId || card?.card_variant_id
  );
  const base = `/TCGs/Pokemon/Sets/${encodeURIComponent(slug)}/Cards/${encodeURIComponent(canonicalId)}`;
  return selectedVariant ? `${base}?variant=${encodeURIComponent(selectedVariant)}` : base;
}

export function buildPokemonCardHref(setSlug, card, variantId = undefined) {
  return buildPokemonCardDetailHref({
    setSlug,
    canonicalCardId: card?.canonicalCardId || card?.canonical_card_id || card?.id,
    cardVariantId: variantId === undefined ? (card?.cardVariantId || card?.card_variant_id) : variantId,
  });
}

export function normalizePokemonCardDetail(payload) {
  if (!payload || typeof payload !== "object") return null;
  const set = payload.set || {};
  return {
    set: {
      ...set,
      // Public route identity is derived independently from internal target
      // identity, including when an older API process still publishes its
      // canonical_key in `slug`.
      slug: toSetSlug(set.name, set.slug),
    },
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

export async function getPokemonCardChaseEfficiency(setId, cardId, variantId, { signal } = {}) {
  const resolvedSet = text(setId), resolvedCard = text(cardId);
  if (!resolvedSet || !resolvedCard) throw new Error("Set and canonical card ids are required");
  const url = new URL(`/api/tcgs/pokemon/sets/${encodeURIComponent(resolvedSet)}/cards/${encodeURIComponent(resolvedCard)}/chase-efficiency`, window.location.origin);
  if (text(variantId)) url.searchParams.set("variant_id", text(variantId));
  const response = await fetch(url, { method: "GET", cache: "no-store", signal });
  let payload = null; try { payload = await response.json(); } catch { payload = null; }
  if (!response.ok) { const error = new Error(payload?.detail?.message || payload?.message || "Unable to load Chase Efficiency"); error.status = response.status; error.code = payload?.detail?.code || payload?.code; throw error; }
  return payload;
}
