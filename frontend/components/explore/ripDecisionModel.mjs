import { readCanonicalBlock } from "./canonicalRipV7.mjs";

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

  let takeaway = "The canonical model inputs are unavailable, so no comparative driver is stated.";
  if (financial.rank !== null && collector.rank !== null) {
    const gap = collector.rank - financial.rank;
    if (gap >= 3) takeaway = "This set ranks primarily because its opening economics compare more favorably with other tracked sets; collector appeal contributes less.";
    else if (gap <= -3) takeaway = "Collector appeal meaningfully lifts this set despite a weaker financial opening profile.";
    else if (overall.rank !== null && overall.cohortSize !== null && overall.rank <= Math.max(3, Math.ceil(overall.cohortSize * 0.25))) takeaway = "Both its opening economics and collector appeal compare strongly with the tracked cohort.";
    else takeaway = "Its financial and collector profiles are similarly placed, and their combined result produces the displayed rank.";
  }

  const rows = [
    ...(Array.isArray(pullRateAssumptions?.rows) ? pullRateAssumptions.rows : []),
    ...(Array.isArray(pullRateAssumptions?.groups) ? pullRateAssumptions.groups.flatMap((group) => Array.isArray(group?.rows) ? group.rows : []) : []),
  ];
  const specialIllustrationRare = rows.find((row) => /special illustration rare/i.test(String(row?.rarity || row?.slotLabel || "")));

  return {
    overall,
    financial,
    collector,
    packCost,
    expectedValue,
    typicalOpening,
    recoverCostProbability,
    verdict,
    takeaway,
    openingOdds: number(specialIllustrationRare?.rarityOddsDenominator) > 0
      ? [{ label: "Special Illustration Rare", denominator: number(specialIllustrationRare.rarityOddsDenominator) }]
      : [],
  };
}
