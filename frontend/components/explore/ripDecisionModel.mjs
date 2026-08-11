import { readCanonicalBlock } from "./canonicalRipV7.mjs";
import { buildRipDrivers } from "./ripDrivers.mjs";
import { getRipQualitativeLabel } from "./ripQualitativeLabel.mjs";
import { normalizeRarityKey, selectPullRateRows } from "../pokemon/set-page/PullRates/pullRateRowsSelector.mjs";

function number(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function buildRipDecisionModel({ canonical, summary = {}, pullRateAssumptions = null } = {}) {
  const overall = readCanonicalBlock(canonical?.overall);
  const financial = readCanonicalBlock(canonical?.financialRip);
  const collector = readCanonicalBlock(canonical?.collectorAppeal);
  const packCost = number(summary.pack_cost);
  const expectedValue = number(summary.mean_value);
  const typicalOpening = number(summary.median_value);
  const recoverCostProbability = number(summary.prob_profit);

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
    verdict,
    qualitativeLabel,
    drivers,
    takeaway,
    openingOdds,
  };
}
