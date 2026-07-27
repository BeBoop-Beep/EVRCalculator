export const CARD_TIMEFRAMES = ["7D", "30D"];

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
      movementFilter: "all",
      sortDirection: losers ? "asc" : "desc",
    };
  }

  if (activeSortMode === "current-price") {
    return {
      sort: activeSortDirection === "desc" ? "market-price-desc" : "market-price-asc",
      movementSort: null,
      movementFilter: "all",
      sortDirection: "asc",
    };
  }

  return {
    sort: activeSortMode === "name" ? "name" : "set-number",
    movementSort: null,
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
