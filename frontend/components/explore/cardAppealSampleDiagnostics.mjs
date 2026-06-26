function toOptionalNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function getDiagnosticMarketPrice(card) {
  const price =
    toOptionalNumber(card?.marketPrice) ??
    toOptionalNumber(card?.market_price) ??
    toOptionalNumber(card?.currentPrice) ??
    toOptionalNumber(card?.current_price);

  return price !== null && price > 0 ? price : null;
}

function getDiagnosticCardAppealScore(card) {
  return toOptionalNumber(card?.adjustedCardAppealScore) ?? toOptionalNumber(card?.adjusted_card_appeal_score);
}

function isPokemonSupertype(card) {
  const supertype = String(card?.supertype ?? "").trim().toLowerCase();
  return supertype === "pokemon" || supertype === "pokémon";
}

function asObject(value) {
  return value && typeof value === "object" ? value : null;
}

function rowsFromCorrelation(correlation) {
  if (!correlation || typeof correlation !== "object") {
    return [];
  }
  if (Array.isArray(correlation.plotRows)) {
    return correlation.plotRows;
  }
  if (Array.isArray(correlation.plot_rows)) {
    return correlation.plot_rows;
  }
  if (Array.isArray(correlation.rows)) {
    return correlation.rows;
  }
  return [];
}

export function hasUsableCardAppealCorrelation(correlation) {
  const rows = rowsFromCorrelation(correlation);
  const n = Number(correlation?.n);
  const plotted = Number(correlation?.plottedCount ?? correlation?.plotted_count);
  return rows.length > 0 || Number.isFinite(n) && n > 0 || Number.isFinite(plotted) && plotted > 0;
}

export function resolvePreferredCardAppealCorrelation({
  explorePayload = null,
  checklistState = null,
  cardsPayload = null,
  previous = null,
} = {}) {
  const candidates = [
    asObject(explorePayload?.cardAppealMarketPriceCorrelation),
    asObject(explorePayload?.card_appeal_market_price_correlation),
    asObject(explorePayload?.cardPayload?.cardAppealMarketPriceCorrelation),
    asObject(explorePayload?.card_payload?.card_appeal_market_price_correlation),
    asObject(explorePayload?.cardsPayload?.cardAppealMarketPriceCorrelation),
    asObject(explorePayload?.cards_payload?.card_appeal_market_price_correlation),
    asObject(explorePayload?.setCards?.cardAppealMarketPriceCorrelation),
    asObject(explorePayload?.set_cards?.card_appeal_market_price_correlation),
    asObject(cardsPayload?.cardAppealMarketPriceCorrelation),
    asObject(cardsPayload?.card_appeal_market_price_correlation),
    asObject(checklistState?.cardAppealMarketPriceCorrelation),
    asObject(previous),
  ];

  for (const candidate of candidates) {
    if (hasUsableCardAppealCorrelation(candidate)) {
      return candidate;
    }
  }
  return null;
}

export function getCardAppealSampleDiagnostics(cards) {
  const rows = Array.isArray(cards) ? cards : [];
  const pricedCards = rows.filter((card) => getDiagnosticMarketPrice(card) !== null);
  const appealScoredCards = rows.filter((card) => getDiagnosticCardAppealScore(card) !== null);
  const pricedAppealCards = pricedCards.filter((card) => getDiagnosticCardAppealScore(card) !== null);
  const excludedNonPokemonPriced = pricedCards.filter(
    (card) => !isPokemonSupertype(card) && getDiagnosticCardAppealScore(card) === null
  );

  return {
    totalCards: rows.length,
    pricedCards: pricedCards.length,
    appealScoredCards: appealScoredCards.length,
    pricedAppealCards: pricedAppealCards.length,
    excludedPricedNoAppeal: pricedCards.length - pricedAppealCards.length,
    excludedNonPokemonPriced: excludedNonPokemonPriced.length,
  };
}
