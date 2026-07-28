export const CARD_TIMEFRAMES = ["7D", "30D"];

// Market Movers ranking metric — independent of direction (gainers/losers) and
// timeframe (7D/30D). "percent" is the canonical default: it is what Market
// Movers ranked by before the metric became selectable. Symbols alone must not
// carry the meaning, so each option keeps a spelled-out accessible label.
export const MARKET_MOVER_METRICS = ["percent", "dollar"];

export const MARKET_MOVER_METRIC_OPTIONS = [
  { value: "dollar", label: "$", accessibleLabel: "Dollar Change" },
  { value: "percent", label: "%", accessibleLabel: "Percentage Change" },
];

export const DEFAULT_MARKET_MOVER_METRIC = "percent";

export function normalizeMarketMoverMetric(value) {
  return MARKET_MOVER_METRICS.includes(value) ? value : DEFAULT_MARKET_MOVER_METRIC;
}

export const ALL_CARDS_SORT_OPTIONS = [
  { value: "set-number", label: "Set Number" },
  { value: "name", label: "Name" },
  { value: "current-price", label: "Current Price" },
];

export function resolveCardsRequest({
  selectedSubTab = "all-cards",
  selectedTimeframe = "7D",
  activeSortMode = "set-number",
  activeSortDirection = "asc",
  activeMovementMetric = DEFAULT_MARKET_MOVER_METRIC,
} = {}) {
  if (selectedSubTab === "market-movers") {
    const losers = activeSortDirection === "losers";
    return {
      sort: "set-number",
      movementSort:
        selectedTimeframe === "30D"
          ? losers
            ? "30d-decliners"
            : "30d-gainers"
          : "7d-movers",
      // Ranking metric is orthogonal to which end of the ranking is shown:
      // direction still picks gainers vs losers, the metric only decides
      // whether the magnitude compared is a percentage or a dollar amount.
      movementMetric: normalizeMarketMoverMetric(activeMovementMetric),
      movementFilter: "all",
      sortDirection: losers ? "asc" : "desc",
    };
  }

  if (activeSortMode === "current-price") {
    return {
      sort: activeSortDirection === "desc" ? "market-price-desc" : "market-price-asc",
      movementSort: null,
      movementMetric: null,
      movementFilter: "all",
      sortDirection: "asc",
    };
  }

  return {
    sort: activeSortMode === "name" ? "name" : "set-number",
    movementSort: null,
    movementMetric: null,
    movementFilter: "all",
    sortDirection: activeSortDirection === "desc" ? "desc" : "asc",
  };
}

export function getAllCardsDirectionLabel(activeSortMode, activeSortDirection) {
  const descending = activeSortDirection === "desc";
  if (activeSortMode === "name") {
    return descending ? "Z → A" : "A → Z";
  }
  if (activeSortMode === "current-price") {
    return descending ? "High → Low" : "Low → High";
  }
  return descending ? "193 → 1" : "1 → 193";
}

export function getEffectiveRarityFilter(selectedSubTab, selectedRarity) {
  return selectedSubTab === "all-cards" ? selectedRarity || null : null;
}
