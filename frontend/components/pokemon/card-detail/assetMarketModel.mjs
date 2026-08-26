export const ASSET_MARKET_WINDOWS = Object.freeze([
  ["1D", "1D"], ["7D", "7D"], ["30D", "30D"], ["3M", "3M"],
  ["6M", "6M"], ["1Y", "1Y"], ["lifetime", "ALL"],
]);

export function finite(value) {
  const parsed = Number(value);
  return value !== null && value !== undefined && Number.isFinite(parsed) ? parsed : null;
}

export function selectAssetMarketWindow(market, requestedWindow) {
  const movement = market?.movements?.[requestedWindow] || { available: false, requestedWindow };
  const all = Array.isArray(market?.history) ? market.history : [];
  const start = movement?.startDate;
  const end = movement?.endDate;
  const history = start && end ? all.filter((point) => point?.date >= start && point?.date <= end) : [];
  return {
    requestedWindow,
    movement,
    history,
    partial: movement?.available === true && movement?.fullCoverage === false,
  };
}

export function movementTone(movement) {
  const amount = finite(movement?.deltaAmount);
  if (amount === null || Math.abs(amount) < 0.005) return "neutral";
  return amount > 0 ? "positive" : "negative";
}
