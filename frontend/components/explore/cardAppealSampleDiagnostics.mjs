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
