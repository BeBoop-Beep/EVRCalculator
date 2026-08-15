export const MARKET_SPARKLINE_MINIMUM_PERCENT_SPAN = 0.03;
export const MARKET_SPARKLINE_DOMAIN_PADDING_RATIO = 0.1;
export const MARKET_SPARKLINE_ABSOLUTE_MINIMUM_SPAN = 0.02;

export function buildMarketSparklineDomain(
  points,
  {
    valueKey = "value",
    minimumPercentSpan = MARKET_SPARKLINE_MINIMUM_PERCENT_SPAN,
    paddingRatio = MARKET_SPARKLINE_DOMAIN_PADDING_RATIO,
    absoluteMinimumSpan = MARKET_SPARKLINE_ABSOLUTE_MINIMUM_SPAN,
  } = {}
) {
  const values = (Array.isArray(points) ? points : [])
    .map((point) => Number(point?.[valueKey] ?? point?.value))
    .filter(Number.isFinite);
  if (values.length === 0) return [0, 1];

  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const midpoint = (minimum + maximum) / 2;
  const observedSpan = maximum - minimum;
  const effectiveSpan = Math.max(
    observedSpan,
    Math.abs(midpoint) * minimumPercentSpan,
    absoluteMinimumSpan
  );
  const halfSpan = effectiveSpan / 2;
  const padding = effectiveSpan * paddingRatio;
  return [midpoint - halfSpan - padding, midpoint + halfSpan + padding];
}
