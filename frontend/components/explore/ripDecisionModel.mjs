import { readCanonicalBlock } from "./canonicalRipV7.mjs";
import { buildRipDrivers } from "./ripDrivers.mjs";
import { getRipQualitativeLabel } from "./ripQualitativeLabel.mjs";
import { normalizeRarityKey, selectPullRateRows } from "../pokemon/set-page/PullRates/pullRateRowsSelector.mjs";

function number(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function firstNumber(...values) {
  for (const value of values) {
    const parsed = number(value);
    if (parsed !== null) return parsed;
  }
  return null;
}

function firstText(...values) {
  for (const value of values) {
    const text = String(value ?? "").trim();
    if (text) return text;
  }
  return null;
}

function firstObject(...values) {
  return values.find((value) => value && typeof value === "object" && !Array.isArray(value)) || null;
}

// Local presentation boundary for newly published decision fields. Probability
// thresholds and spend are read verbatim; this adapter never recalculates them.
export function selectRipDecisionFields({ canonical, summary = {}, chaseCards = [] } = {}) {
  const raw = firstObject(canonical?.decisionMetrics, canonical?.decision_metrics, summary?.decision_metrics, summary?.decisionMetrics) || {};
  const source = firstObject(raw?.topChase, raw?.top_chase, canonical?.topChase, canonical?.top_chase, summary?.top_chase, summary?.topChase);
  const topChase = source ? {
    name: firstText(source.name, source.card_name, source.cardName),
    imageUrl: firstText(source.image_url, source.imageUrl, source.image_small_url, source.imageSmallUrl),
    marketValue: firstNumber(source.market_value, source.marketValue, source.market_price, source.marketPrice),
    probability: firstNumber(source.probability, source.probability_per_opening, source.probabilityPerOpening, source.pull_probability),
    oddsDenominator: firstNumber(source.odds_denominator, source.oddsDenominator, source.one_in_x, source.oneInX),
    openings50: firstNumber(source.openings_for_50_percent, source.openingsFor50Percent, source.packs_for_50_percent, source.packsFor50Percent),
    openings90: firstNumber(source.openings_for_90_percent, source.openingsFor90Percent, source.packs_for_90_percent, source.packsFor90Percent),
    spend50: firstNumber(source.spend_for_50_percent, source.spendFor50Percent, source.cost_for_50_percent, source.costFor50Percent),
    spend90: firstNumber(source.spend_for_90_percent, source.spendFor90Percent, source.cost_for_90_percent, source.costFor90Percent),
  } : null;
  return {
    breakEvenValue: firstNumber(raw?.break_even_value, raw?.breakEvenValue, summary?.break_even_value, summary?.breakEvenValue),
    expectedReturnRate: firstNumber(raw?.expected_return_rate, raw?.expectedReturnRate, summary?.expected_return_rate, summary?.expectedReturnRate),
    expectedEdge: firstNumber(raw?.expected_edge, raw?.expectedEdge, summary?.expected_edge, summary?.expectedEdge),
    topChase: topChase && (topChase.name || topChase.marketValue !== null) ? topChase : null,
    marketChaseCards: (Array.isArray(chaseCards) ? chaseCards : []).filter((card) => card?.name || card?.cardName || card?.card_name).slice(0, 4),
  };
}

export function buildRipDecisionModel({ canonical, summary = {}, pullRateAssumptions = null, chaseCards = [] } = {}) {
  const overall = readCanonicalBlock(canonical?.overall);
  const financial = readCanonicalBlock(canonical?.financialRip);
  const collector = readCanonicalBlock(canonical?.collectorAppeal);
  const packCost = number(summary.pack_cost);
  const expectedValue = number(summary.mean_value);
  const typicalOpening = number(summary.median_value);
  const recoverCostProbability = number(summary.prob_profit);
  const expectedLoss = firstNumber(summary.expected_loss_per_pack, summary.expectedLossPerPack);
  const decision = selectRipDecisionFields({ canonical, summary, chaseCards });

  let verdict = "Canonical RIP ranking is unavailable for this set.";
  if (overall.rank !== null && overall.cohortSize !== null) {
    const leading = overall.rank <= Math.max(3, Math.ceil(overall.cohortSize * 0.2));
    const economicsBelowCost = packCost !== null && expectedValue !== null && expectedValue < packCost;
    if (leading && economicsBelowCost) verdict = "One of the strongest relative opening options, though expected returns remain below pack cost.";
    else if (leading) verdict = "One of the strongest relative opening options in the currently tracked set cohort.";
    else if (economicsBelowCost) verdict = "A middle-of-the-pack opening option with expected returns below today's pack cost.";
    else verdict = "Its combined opening economics and collector appeal place it in the middle of the tracked cohort.";
  }

  // HELPS / HURTS / RESULT and the takeaway are one deterministic decision, so
  // the sentence can never contradict the labels shown above it.
  const drivers = buildRipDrivers({ financial, collector, overall });
  const takeaway = drivers.takeaway;
  const qualitativeLabel = getRipQualitativeLabel({
    tier: overall.tier,
    rank: overall.rank,
    cohortSize: overall.cohortSize,
  });

  const consumerPriority = new Map([
    ["illustration rare", 1],
    ["ultra rare", 2],
    ["special illustration rare", 3],
    ["hyper rare", 4],
    ["double rare", 5],
  ]);
  const openingOdds = selectPullRateRows(pullRateAssumptions)
    .map(({ row, groupKey }) => ({
      label: String(row?.rarity || "").trim(),
      rarityKey: normalizeRarityKey(row?.rarity),
      denominator: number(row?.rarityOddsDenominator),
      groupKey,
    }))
    .filter((row) => row.label && row.denominator > 0 && (row.groupKey === "hit_rarity_model" || consumerPriority.has(row.rarityKey)))
    .sort((left, right) => (consumerPriority.get(left.rarityKey) ?? 20) - (consumerPriority.get(right.rarityKey) ?? 20))
    .slice(0, 3)
    .map(({ label, denominator }) => ({
      label: label.replace(/\b\w/g, (letter) => letter.toUpperCase()),
      denominator,
    }));

  return {
    overall,
    financial,
    collector,
    packCost,
    expectedValue,
    typicalOpening,
    recoverCostProbability,
    expectedLoss,
    decision,
    verdict,
    qualitativeLabel,
    drivers,
    takeaway,
    openingOdds,
  };
}
