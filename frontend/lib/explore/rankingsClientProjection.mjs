// The exact target fields the Rankings table needs on the CLIENT — and nothing
// else.
//
// WHY THIS EXISTS
// ---------------
// `ExploreTableClient` is "use client", so every property of every object handed
// to it is serialized into the RSC flight payload and shipped to the browser.
// /Rankings was passing whole canonical targets, which made the delivered
// document ~1.34 MB (186 KB gzipped) — the largest transfer on the site, and
// ~5.5x /Market's after Market received the same treatment.
//
// THIS IS A SERVER->CLIENT (RSC) OPTIMIZATION ONLY.
// It does NOT improve the backend DB/PostgREST targets fetch: the page still
// requests the complete canonical cohort through `getRipStatisticsTargets`,
// deliberately, because that is the shared cache identity Rankings, /Market and
// set detail all reuse. Narrowing the backend request is a separate question and
// is not what this file does.
//
// THE CONTRACT IS WIDER THAN /Market's
// ------------------------------------
// /Market's ladder reads 12 scalar fields. Rankings renders seven sortable
// columns, 1D rank movement for two metrics, and eight ranking modes — so its
// projection is necessarily larger. It is NOT a superset-by-accident: every path
// below is traced to a consumer in the audit that accompanies this module.
//
// HIDDEN MODES ARE RETAINED ON PURPOSE
// ------------------------------------
// `RANKING_MODE_PICKER_ENABLED` is false today, but exploreRankingConfig.mjs
// states the alternative lenses are kept for future paid functionality. Dropping
// their fields because the control is currently hidden would turn a hidden
// feature into a broken one the moment the flag flips, and the failure would be
// silent (every score reads `null` and renders "Unavailable"). Every field of
// every mode in EXPLORE_RANKING_MODES is therefore projected, visible or not.
//
// Both casings are kept wherever a consumer reads camelCase with a snake_case
// fallback; dropping either half would blank a cell on whichever spelling the
// publication happens to carry.

/** Scalar (top-level) keys, each traced to a consumer. */
const SCALAR_FIELDS = Object.freeze([
  // identity + routing: SetIdentity, buildTcgSetHrefFromTarget, row keys
  "target_type",
  "target_id",
  "set_id",
  "id",
  "name",
  "era",
  "canonical_key",
  "logo_image_url",
  "symbol_image_url",

  // sortable columns: rankingsSort.RANKINGS_SORT_COLUMNS
  "mean_value",                 // EV
  "median_value",               // Typical Opening / P50
  "medianValue",
  "modelBreakEvenPrice",
  "model_break_even_price",
  "pack_cost",                  // Market Pack Price
  "prob_profit",                // Chance to Beat Cost
  "expected_loss_when_losing",  // Average Loss
  "expectedLossWhenLosing",
  "top_chase_name", "top_chase_market_value", "top_chase_one_in_packs",
  "modeled_packs_to_50", "modeled_spend_to_50",

  // 1D rank movement: ExploreTableClient -> formatRankMovement
  "previousOverallRipRank1d",
  "previous_overall_rip_rank_1d",
  "overallRipRankComparisonStatus1d",
  "overall_rip_rank_comparison_status_1d",
  "previousFinancialRipRank1d",
  "previous_financial_rip_rank_1d",
  "financialRipRankComparisonStatus1d",
  "financial_rip_rank_comparison_status_1d",

  // ranking-mode scalar fields (hidden but supported — see module note)
  "relative_experience_score", "experience_rank", "experience_tier",
  "relative_chase_potential_score", "chase_potential_rank", "chase_potential_tier",
  "mean_value_to_cost_ratio", "mean_value_to_cost_rank", "mean_value_to_cost_tier",
  "median_value_to_cost_ratio",
  "relative_biggest_upside_score", "biggest_upside_rank", "biggest_upside_tier",
  "p99_value_to_cost_ratio", "p99_value_to_cost_rank", "p99_value_to_cost_tier",
]);

/**
 * Nested blocks, projected leaf-by-leaf.
 *
 * `overallRipV8` / `financialRipV3` are read at TOP LEVEL by
 * exploreRankingConfig's dot-paths, and are also what `resolveCanonicalRipV7`
 * falls back to. `publicRipContractV8` is read by `resolveCanonicalRipV7`, which
 * is the ONLY source of Collector Appeal — there is no top-level V3 appeal block.
 *
 * All three contract blocks are kept together rather than just `collectorAppeal`:
 * the resolver picks `publicRipContractV8` whenever it has ANY content and then
 * reads overall/financialRip from it, so shipping a contract containing only the
 * appeal block would hand any future resolver caller an empty Overall RIP. The
 * contract's `audit` block is NOT projected — `readCanonicalBlock` never reads
 * it, and it is the single heaviest thing in the contract.
 */
const BLOCK_LEAVES = Object.freeze({
  setRipV1: ["score", "tier", "rank", "cohortSize", "rankable", "methodologyVersion", "participatingFamilyCount", "participatingFamilies", "skuEvidenceCount", "familyScores", "displayFamilyScores"],
  overallRipV8: ["relativeScore", "rank", "cohortSize", "tier"],
  overallRipV9: ["relativeScore", "rank", "cohortSize", "tier"],
  overallRipV10: ["relativeScore", "leaderNormalizedScore", "rank", "cohortSize", "rankedSetCount", "tier", "status", "statusReason"],
  financialRipV3: ["relativeScore", "rank", "cohortSize", "tier"],
  financialRipV4: ["relativeScore", "leaderNormalizedScore", "rank", "cohortSize", "rankedSetCount", "tier", "status", "statusReason"],
  universalSetDesirability: ["score", "rank", "rankedSetCount"],
  rankingsChase: ["cardName", "currentMarketPrice", "impliedOddsOneInN", "packsFor50PercentChance"],
  topChase: ["cardName", "currentMarketPrice", "impliedOddsOneInN", "packsFor50PercentChance"],
  top_chase: ["card_name", "current_market_price", "implied_odds_one_in_n", "packs_for_50_percent_chance"],
  ripDecision: ["topChase"],
  rip_decision: ["top_chase"],
});

/** The canonical-contract blocks `readCanonicalBlock` consumes, leaf by leaf. */
const CONTRACT_BLOCKS = Object.freeze(["overallRip", "financialRip", "collectorAppeal"]);
const CONTRACT_LEAVES = Object.freeze([
  "relativeScore", "leaderNormalizedScore", "absoluteScore", "score", "rank", "tier", "publicTier",
  "rankedSetCount", "cohortSize", "status", "statusReason",
]);

function projectLeaves(source, leaves) {
  if (!source || typeof source !== "object") return undefined;
  const out = {};
  let present = false;
  for (const leaf of leaves) {
    if (source[leaf] !== undefined) {
      out[leaf] = source[leaf];
      present = true;
    }
  }
  return present ? out : undefined;
}

function projectContract(contract) {
  if (!contract || typeof contract !== "object") return undefined;
  const out = {};
  let present = false;
  for (const block of CONTRACT_BLOCKS) {
    const projected = projectLeaves(contract[block], CONTRACT_LEAVES);
    if (projected !== undefined) {
      out[block] = projected;
      present = true;
    }
  }
  return present ? out : undefined;
}

function projectTarget(target) {
  if (!target || typeof target !== "object") return target;
  const out = {};

  for (const field of SCALAR_FIELDS) {
    if (target[field] !== undefined) out[field] = target[field];
  }

  for (const [block, leaves] of Object.entries(BLOCK_LEAVES)) {
    const projected = projectLeaves(target[block], leaves);
    if (projected !== undefined) out[block] = projected;
  }

  const contract = projectContract(target.publicRipContractV8);
  if (contract !== undefined) out.publicRipContractV8 = contract;
  const contractV9 = projectContract(target.publicRipContractV9);
  if (contractV9 !== undefined) out.publicRipContractV9 = contractV9;
  const contractV10 = projectContract(target.publicRipContractV10);
  if (contractV10 !== undefined) out.publicRipContractV10 = contractV10;

  return out;
}

/**
 * Project the leaderboard's targets for the client boundary.
 *
 * Order is preserved exactly: the incoming array is already in canonical Overall
 * RIP V7 rank order (resolved server-side), and `sortRankingsRows` treats that
 * order as its tie-break and as the default view. Reordering here would change
 * the leaderboard.
 */
export function projectRankingsTargets(targets) {
  return Array.isArray(targets) ? targets.map(projectTarget) : [];
}

/** Flat list of every projected path, for tests and audit reporting. */
export const RANKINGS_CLIENT_FIELDS = Object.freeze([
  ...SCALAR_FIELDS,
  ...Object.entries(BLOCK_LEAVES).flatMap(([b, ls]) => ls.map((l) => `${b}.${l}`)),
  ...["publicRipContractV8", "publicRipContractV9", "publicRipContractV10"].flatMap((contract) =>
    CONTRACT_BLOCKS.flatMap((b) => CONTRACT_LEAVES.map((l) => `${contract}.${b}.${l}`))
  ),
]);

export { SCALAR_FIELDS, BLOCK_LEAVES, CONTRACT_BLOCKS, CONTRACT_LEAVES };
