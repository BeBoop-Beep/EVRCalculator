import { buildMarketSparklineDomain } from "./marketSparklineDomain.mjs";

export const MARKET_INDEX_REFERENCE_VALUE = 100;

export function buildMarketPerformanceDomain(points) {
  return buildMarketSparklineDomain(
    [...(Array.isArray(points) ? points : []), { value: MARKET_INDEX_REFERENCE_VALUE }],
    { valueKey: "value" }
  );
}
