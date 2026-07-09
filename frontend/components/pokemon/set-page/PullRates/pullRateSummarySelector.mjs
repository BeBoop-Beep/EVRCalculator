import {
  buildGroupsForRender,
  formatOddsDenominator,
  formatPullFrequency,
  formatRarityLabel,
} from "./pullRateFormatting.mjs";

// Derives 2-3 headline stats for the Hit Rate Summary section (priority 2)
// from the same pullRateAssumptions payload the full table already uses — no
// new fetch, no invented data. Picks the pack_structure row with the rarest
// (highest) specific-card odds denominator as the "chase" headline, since
// that's the rarity/slot collectors are most likely to care about at a
// glance.
export function selectPullRateHeadline(pullRateAssumptions) {
  const groups = buildGroupsForRender(pullRateAssumptions);
  const packStructure = groups.find((group) => group.key === "pack_structure") || groups[0] || null;
  if (!packStructure || packStructure.rows.length === 0) {
    return null;
  }

  const rows = packStructure.rows;
  const bestRow = rows.reduce((best, row) => {
    const denom = Number(row.specificCardOddsDenominator ?? row.specific_card_odds_denominator) || 0;
    const bestDenom = best
      ? Number(best.specificCardOddsDenominator ?? best.specific_card_odds_denominator) || 0
      : -1;
    return denom > bestDenom ? row : best;
  }, null);

  return {
    trackedRarityCount: rows.length,
    headlineRarityLabel: bestRow ? formatRarityLabel(bestRow.rarity) : null,
    headlinePullFrequency: bestRow ? formatPullFrequency(bestRow, packStructure.key) : null,
    headlineSpecificOdds: bestRow
      ? formatOddsDenominator(bestRow.specificCardOddsDenominator ?? bestRow.specific_card_odds_denominator)
      : null,
  };
}
