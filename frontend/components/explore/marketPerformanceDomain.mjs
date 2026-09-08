import { buildMarketSparklineDomain } from "./marketSparklineDomain.mjs";

export const MARKET_INDEX_REFERENCE_VALUE = 100;
export const MARKET_INDEX_SHORT_WINDOW_MINIMUM_PERCENT_SPAN = 0.0075;
export const MARKET_INDEX_SHORT_WINDOWS = new Set(["1D", "7D", "30D", "3M"]);

export function buildMarketPerformanceDomain(points, timeframe = "All") {
  const visible = Array.isArray(points) ? points : [];
  if (MARKET_INDEX_SHORT_WINDOWS.has(timeframe)) {
    return buildMarketSparklineDomain(visible, {
      valueKey: "value",
      minimumPercentSpan: MARKET_INDEX_SHORT_WINDOW_MINIMUM_PERCENT_SPAN,
      paddingRatio: 0.12,
    });
  }
  return buildMarketSparklineDomain(
    [...visible, { value: MARKET_INDEX_REFERENCE_VALUE }],
    { valueKey: "value" }
  );
}
