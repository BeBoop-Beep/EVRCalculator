import { readCanonicalBlock, resolveCanonicalRipV7 } from "./canonicalRipV7.mjs";
import { readModelBreakEven, readTypicalOpening, readModeledReturnPercent, normalizeProbability } from "./rankingsSort.mjs";
import { readOptionalRankingsChase } from "./rankingsPresentation.mjs";

const number = (value) => value === null || value === undefined || value === "" || !Number.isFinite(Number(value)) ? null : Number(value);

export function readFinancialSetRanking(target) {
  const block = target?.financialRipV4 || {};
  return { publicScore: number(block.leaderNormalizedScore), rank: number(block.rank), cohortSize: number(block.cohortSize ?? block.rankedSetCount), tier: block.tier || null, status: block.status || null, statusReason: block.statusReason || null, typicalOpening: readTypicalOpening(target), modelBreakEven: readModelBreakEven(target), modeledReturnPercent: readModeledReturnPercent(target), chanceToBeatCost: normalizeProbability(target?.prob_profit) };
}

export function readSetCollectorAppealRanking(target) {
  const headline = readCanonicalBlock(resolveCanonicalRipV7(target).collectorAppeal);
  const components = target?.publicCollectorAppealContractV1?.components || {};
  const roster = components.rosterDesirability || {};
  const frequency = components.desirableOutcomeFrequency || {};
  return { publicScore: headline.publicScore, rank: headline.rank, cohortSize: headline.cohortSize, tier: headline.tier, status: headline.status, statusReason: headline.statusReason, rosterScore: number(roster.score), frequencyRawValue: number(frequency.rawValue), frequencyDisplayPercent: number(frequency.displayPercent) };
}

export function readChaseAccessibilitySetRanking(target) {
  const block = target?.setRipV1?.chaseAccessibility || {};
  return { block, publicScore: number(block.publicScore), rank: number(block.setRank), cohortSize: number(block.setCohortSize), tier: block.tier || null, chaseDepth: number(block.chaseDepth), status: block.status || null, statusReason: block.statusReason || null, chase: readOptionalRankingsChase(target) };
}

export function canonicalMetricRows(targets, read, eraFilter = null, query = "") {
  const era = String(eraFilter || "").trim().toLowerCase();
  const needle = String(query || "").trim().toLowerCase();
  return [...(Array.isArray(targets) ? targets : [])].sort((a, b) => { const ar = read(a).rank; const br = read(b).rank; if (ar !== null && br !== null && ar !== br) return ar - br; if (ar !== null) return -1; if (br !== null) return 1; return String(a?.name || "").localeCompare(String(b?.name || "")); }).filter((target) => (!era || String(target?.era || "").trim().toLowerCase() === era) && (!needle || String(target?.name || "").toLowerCase().includes(needle)));
}
