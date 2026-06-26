import { toOptionalNumber, toOptionalString } from "../sharedStats.mjs";

function normalizeCard(card) {
  return {
    ...card,
    id: toOptionalString(card?.id ?? card?.cardId ?? card?.card_id),
    name: toOptionalString(card?.name ?? card?.cardName ?? card?.card_name),
    setId: toOptionalString(card?.setId ?? card?.set_id),
    currentPrice: toOptionalNumber(card?.currentPrice ?? card?.current_price ?? card?.marketPrice ?? card?.market_price),
    marketPrice: toOptionalNumber(card?.marketPrice ?? card?.market_price ?? card?.currentPrice ?? card?.current_price),
    subjectDemandScore: toOptionalNumber(
      card?.subjectDemandScore ??
        card?.subject_demand_score ??
        card?.pokemonDesirabilityScore ??
        card?.pokemon_desirability_score ??
        card?.cardDesirabilityScore ??
        card?.card_desirability_score
    ),
  };
}

export function selectCards(payload = {}) {
  const rawCards = Array.isArray(payload?.cards)
    ? payload.cards
    : Array.isArray(payload?.cardPayload?.cards)
    ? payload.cardPayload.cards
    : Array.isArray(payload?.card_payload?.cards)
    ? payload.card_payload.cards
    : Array.isArray(payload?.cardsPayload?.cards)
    ? payload.cardsPayload.cards
    : Array.isArray(payload?.cards_payload?.cards)
    ? payload.cards_payload.cards
    : Array.isArray(payload?.setCards?.cards)
    ? payload.setCards.cards
    : Array.isArray(payload?.set_cards?.cards)
    ? payload.set_cards.cards
    : Array.isArray(payload?.payload_json?.cards)
    ? payload.payload_json.cards
    : Array.isArray(payload)
    ? payload
    : [];
  const cards = rawCards.map(normalizeCard).filter((card) => card.id || card.name);
  const correlation =
    payload?.cardAppealMarketPriceCorrelation ||
    payload?.card_appeal_market_price_correlation ||
    payload?.cardPayload?.cardAppealMarketPriceCorrelation ||
    payload?.card_payload?.card_appeal_market_price_correlation ||
    payload?.cardsPayload?.cardAppealMarketPriceCorrelation ||
    payload?.cards_payload?.card_appeal_market_price_correlation ||
    payload?.setCards?.cardAppealMarketPriceCorrelation ||
    payload?.set_cards?.card_appeal_market_price_correlation ||
    payload?.meta?.cardAppealMarketPriceCorrelation ||
    payload?.meta?.card_appeal_market_price_correlation ||
    null;
  return {
    cards,
    cardAppealMarketPriceCorrelation: correlation,
    diagnostics: {
      source: Array.isArray(payload?.cards) ? "cards_payload" : "cards_snapshot_payload",
      totalRows: rawCards.length,
      renderedRows: cards.length,
      pricedRows: cards.filter((card) => card.marketPrice !== null).length,
      demandRows: cards.filter((card) => card.subjectDemandScore !== null).length,
    },
  };
}
