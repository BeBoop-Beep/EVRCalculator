function toOptionalString(value) {
  const text = String(value || "").trim();
  return text || null;
}

function toOptionalNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizePayload(payload) {
  const cards = Array.isArray(payload?.cards) ? payload.cards : [];

  return {
    set: {
      id: toOptionalString(payload?.set?.id),
      name: toOptionalString(payload?.set?.name),
      slug: toOptionalString(payload?.set?.slug),
    },
    cards: cards.map((card) => ({
      id: toOptionalString(card?.id),
      name: toOptionalString(card?.name),
      setId: toOptionalString(card?.set_id ?? card?.setId),
      setName: toOptionalString(card?.set_name ?? card?.setName),
      pokemonTcgApiCardId: toOptionalString(card?.pokemon_tcg_api_card_id ?? card?.pokemonTcgApiCardId),
      cardNumber: toOptionalString(card?.card_number ?? card?.collector_number ?? card?.number),
      printedNumber: toOptionalString(card?.printed_number ?? card?.printedNumber),
      rarity: toOptionalString(card?.rarity),
      supertype: toOptionalString(card?.supertype),
      subtypes: Array.isArray(card?.subtypes) ? card.subtypes.map(toOptionalString).filter(Boolean) : [],
      nationalPokedexNumbers: Array.isArray(card?.national_pokedex_numbers ?? card?.nationalPokedexNumbers)
        ? (card?.national_pokedex_numbers ?? card?.nationalPokedexNumbers).map(toOptionalNumber).filter((value) => value !== null)
        : [],
      imageSmallUrl: toOptionalString(card?.image_small_url ?? card?.small_image_url),
      imageLargeUrl: toOptionalString(card?.image_large_url ?? card?.large_image_url),
      marketPrice: toOptionalNumber(card?.market_price ?? card?.estimated_market_price),
      tcgplayerProductId: toOptionalString(card?.tcgplayer_product_id),
    })),
    meta: payload?.meta || { dedupe: {}, sources: {}, timings: {} },
  };
}

export async function getPokemonSetCards(setId) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    throw new Error("Set id is required");
  }

  const response = await fetch(
    `/api/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/cards`,
    {
      method: "GET",
      cache: "no-store",
    }
  );

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const message = payload?.message || payload?.error || "Unable to load set cards";
    const requestError = new Error(message);
    requestError.status = response.status;
    throw requestError;
  }

  return normalizePayload(payload);
}
