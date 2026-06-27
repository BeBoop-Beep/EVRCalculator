function toOptionalNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function toObject(value) {
  return value && typeof value === "object" ? value : {};
}

function normalizeProbability(value) {
  const parsed = toOptionalNumber(value);
  if (parsed === null) return null;
  return parsed > 1 ? parsed / 100 : parsed;
}

const HIGHER_IS_BETTER = new Set([
  "ripScore",
  "profitScore",
  "safetyScore",
  "desirabilityScore",
  "stabilityScore",
  "setValue",
  "meanValue",
  "averageHitValue",
  "probProfit",
  "probBigHit",
  "meanCostRatio",
  "medianCostRatio",
  "p95CostRatio",
  "p99ValueToCostRatio",
  "effectiveChaseCount",
]);

const LOWER_IS_BETTER = new Set([
  "averageLoss",
  "chanceToMissPackCost",
  "expectedLossWhenLosing",
  "medianLossWhenLosing",
  "p05ShortfallToCost",
  "coefficientOfVariation",
  "hhiEvConcentration",
]);

export function getTrendDirection(metricKey) {
  if (LOWER_IS_BETTER.has(metricKey)) return "lower";
  if (HIGHER_IS_BETTER.has(metricKey)) return "higher";
  return "neutral";
}

export function resolveTrend({ currentValue, previousValue, metricKey }) {
  const current = toOptionalNumber(currentValue);
  const previous = toOptionalNumber(previousValue);
  if (current === null || previous === null || current === previous) {
    return { trend: current === previous && current !== null ? "flat" : "unknown", isImprovement: null, source: "trendScoresSelector" };
  }
  const direction = getTrendDirection(metricKey);
  const trend = current > previous ? "up" : "down";
  const isImprovement =
    direction === "neutral" ? null : direction === "higher" ? current > previous : current < previous;
  return { trend, isImprovement, source: "trendScoresSelector" };
}

export function selectTrendScores({ summary = {}, previousPoint = {}, setValueMetrics = null } = {}) {
  const safeSummary = toObject(summary);
  const safePreviousPoint = toObject(previousPoint);
  const safeSetValueMetrics = setValueMetrics && typeof setValueMetrics === "object" ? setValueMetrics : null;

  const fields = {
    ripScore: [safeSummary.relative_pack_score ?? safeSummary.pack_score, safePreviousPoint.relativePackScore ?? safePreviousPoint.packScore],
    profitScore: [safeSummary.relative_profit_score ?? safeSummary.profit_score, safePreviousPoint.relativeProfitScore ?? safePreviousPoint.profitScore],
    safetyScore: [safeSummary.relative_safety_score ?? safeSummary.safety_score, safePreviousPoint.relativeSafetyScore ?? safePreviousPoint.safetyScore],
    desirabilityScore: [
      safeSummary.relative_desirability_score ?? safeSummary.desirability_score,
      safePreviousPoint.relativeDesirabilityScore ?? safePreviousPoint.desirabilityScore,
    ],
    stabilityScore: [
      safeSummary.relative_stability_score ?? safeSummary.stability_score,
      safePreviousPoint.relativeStabilityScore ?? safePreviousPoint.stabilityScore,
    ],
    packCost: [safeSummary.pack_cost, safePreviousPoint.packCost],
    setValue: [safeSetValueMetrics?.value ?? safeSummary.current_checklist_set_value, safePreviousPoint.setValue],
    meanValue: [safeSummary.mean_value, safePreviousPoint.meanValue],
    averageHitValue: [safeSummary.average_hit_value, safePreviousPoint.averageHitValue],
    probProfit: [normalizeProbability(safeSummary.prob_profit), normalizeProbability(safePreviousPoint.probProfit)],
    probBigHit: [normalizeProbability(safeSummary.prob_big_hit), normalizeProbability(safePreviousPoint.probBigHit)],
  };

  return Object.fromEntries(
    Object.entries(fields).map(([metricKey, [currentValue, previousValue]]) => [
      metricKey,
      resolveTrend({ currentValue, previousValue, metricKey }),
    ])
  );
}
