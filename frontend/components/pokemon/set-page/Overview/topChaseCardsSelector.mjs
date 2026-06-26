import { toOptionalNumber, toOptionalString } from "../sharedStats.mjs";

function normalizeCard(card, index) {
  const id = toOptionalString(card?.id ?? card?.cardId ?? card?.card_id ?? card?.cardVariantId ?? card?.card_variant_id);
  const name = toOptionalString(card?.name ?? card?.cardName ?? card?.card_name);
  return {
    ...card,
    id,
    cardId: toOptionalString(card?.cardId ?? card?.card_id ?? id),
    cardVariantId: toOptionalString(card?.cardVariantId ?? card?.card_variant_id),
    name,
    rank: toOptionalNumber(card?.rank ?? card?.marketRank ?? card?.market_rank) ?? index + 1,
    marketPrice: toOptionalNumber(card?.marketPrice ?? card?.market_price ?? card?.estimatedMarketPrice ?? card?.estimated_market_price),
    priceHistory: Array.isArray(card?.priceHistory)
      ? card.priceHistory.map((point) => ({ ...point }))
      : Array.isArray(card?.price_history)
      ? card.price_history.map((point) => ({ ...point }))
      : [],
  };
}

export function selectTopChaseCards(payload = {}) {
  const rawCards = Array.isArray(payload?.topChaseCards)
    ? payload.topChaseCards
    : Array.isArray(payload?.top_chase_cards)
    ? payload.top_chase_cards
    : Array.isArray(payload?.topMarketCards)
    ? payload.topMarketCards
    : Array.isArray(payload?.top_market_cards)
    ? payload.top_market_cards
    : Array.isArray(payload?.marketDashboard?.topChaseCards)
    ? payload.marketDashboard.topChaseCards
    : Array.isArray(payload?.marketDashboard?.top_chase_cards)
    ? payload.marketDashboard.top_chase_cards
    : Array.isArray(payload?.marketDashboard?.topMarketCards)
    ? payload.marketDashboard.topMarketCards
    : Array.isArray(payload?.marketDashboard?.top_market_cards)
    ? payload.marketDashboard.top_market_cards
    : Array.isArray(payload?.market_dashboard?.topMarketCards)
    ? payload.market_dashboard.topMarketCards
    : Array.isArray(payload?.market_dashboard?.top_market_cards)
    ? payload.market_dashboard.top_market_cards
    : Array.isArray(payload?.cards)
    ? payload.cards
    : [];
  const diagnostics = {
    source: "top_chase_cards",
    totalRows: rawCards.length,
    missingIdentityRows: 0,
    emptyRenderableRows: 0,
  };
  const cards = rawCards
    .map(normalizeCard)
    .filter((card) => {
      const isRenderable = Boolean(card.id || card.name);
      if (!isRenderable) diagnostics.emptyRenderableRows += 1;
      if (!card.id) diagnostics.missingIdentityRows += 1;
      return isRenderable;
    });

  return {
    cards,
    marketMovers:
      payload?.marketMovers ||
      payload?.market_movers ||
      payload?.marketDashboard?.marketMovers ||
      payload?.marketDashboard?.market_movers ||
      payload?.market_dashboard?.marketMovers ||
      payload?.market_dashboard?.market_movers ||
      { heatingUp: [], coolingOff: [], all: [] },
    diagnostics,
  };
}
