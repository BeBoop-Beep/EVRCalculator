import { buildMarketSparklineDomain } from "./marketSparklineDomain.mjs";

export const MARKET_INDEX_REFERENCE_VALUE = 100;
export const MARKET_CHART_VIEW_PERFORMANCE = "performance";
export const MARKET_CHART_VIEW_INDEX = "index";
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

export function toSelectedWindowPerformance(values = []) {
  const baseline = values.find((value) => Number.isFinite(value));
  return values.map((value) => Number.isFinite(value) && Number.isFinite(baseline) && baseline !== 0
    ? ((value / baseline) - 1) * 100
    : null);
}

export function projectMarketChartValues(values = [], viewMode = MARKET_CHART_VIEW_PERFORMANCE) {
  return viewMode === MARKET_CHART_VIEW_INDEX ? [...values] : toSelectedWindowPerformance(values);
}

export function isMarketIndexReferenceVisible(domain = []) {
  const [minimum, maximum] = domain;
  return Number.isFinite(minimum)
    && Number.isFinite(maximum)
    && minimum <= MARKET_INDEX_REFERENCE_VALUE
    && maximum >= MARKET_INDEX_REFERENCE_VALUE;
}

export function buildRelativePerformanceDomain(points) {
  const values = (points || []).map((point) => Number(point?.value)).filter(Number.isFinite);
  const low = Math.min(0, ...values);
  const high = Math.max(0, ...values);
  const movement = high - low;
  const span = Math.max(0.75, movement * 1.24);
  const center = (high + low) / 2;
  let min = center - span / 2;
  let max = center + span / 2;
  if (min > 0) min = 0;
  if (max < 0) max = 0;
  return [min, max];
}
