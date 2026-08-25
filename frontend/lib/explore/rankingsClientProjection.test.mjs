import assert from "node:assert/strict";
import test from "node:test";

import {
  EXPLORE_RANKING_MODES,
  getScoreForMode,
  getRankForMode,
  getRankedSetCountForMode,
  getTierForMode,
} from "../../constants/exploreRankingConfig.mjs";
import {
  RANKINGS_SORT_COLUMNS,
  SORT_ASC,
  SORT_DESC,
  readAverageLoss,
  readCollectorAppealBlock,
  readSortValue,
  sortRankingsRows,
} from "../../components/explore/rankingsSort.mjs";
import { projectRankingsTargets, RANKINGS_CLIENT_FIELDS } from "./rankingsClientProjection.mjs";
import { readCanonicalOverallRipV10 } from "../../components/explore/canonicalRipV7.mjs";

/** A target carrying every field the table reads, plus the heavy blocks it does not. */
function target(i, overrides = {}) {
  return {
    target_type: "set",
    target_id: `set-${i}`,
    set_id: `set-${i}`,
    id: `set-${i}`,
    name: `Set ${i}`,
    era: "Scarlet & Violet",
    logo_image_url: `https://images.pokemontcg.io/${i}-logo.png`,
    symbol_image_url: `https://images.pokemontcg.io/${i}-symbol.png`,

    mean_value: 10 + i,
    pack_cost: 4 + i,
    prob_profit: 0.3 + i / 100,
    expected_loss_when_losing: 2 + i,

    previousOverallRipRank1d: i + 1,
    overallRipRankComparisonStatus1d: "available",
    previousFinancialRipRank1d: i + 2,
    financialRipRankComparisonStatus1d: "available",

    relative_experience_score: 50 + i, experience_rank: i, experience_tier: "B",
    relative_chase_potential_score: 40 + i, chase_potential_rank: i, chase_potential_tier: "C",
    mean_value_to_cost_ratio: 1 + i / 10, mean_value_to_cost_rank: i, mean_value_to_cost_tier: "A",
    relative_biggest_upside_score: 60 + i, biggest_upside_rank: i, biggest_upside_tier: "S",
    p99_value_to_cost_ratio: 3 + i / 10, p99_value_to_cost_rank: i, p99_value_to_cost_tier: "A",

    overallRipV8: { relativeScore: 90 - i, rank: i, cohortSize: 22, tier: "S", absoluteScore: 70 - i },
    overallRipV10: { relativeScore: 90 - i, leaderNormalizedScore: 90 - i, rank: i, cohortSize: 22, tier: "S", absoluteScore: 70 - i },
    financialRipV3: { relativeScore: 80 - i, rank: i, cohortSize: 22, tier: "A", absoluteScore: 60 - i },
    financialRipV4: { relativeScore: 80 - i, leaderNormalizedScore: 80 - i, rank: i, cohortSize: 22, tier: "A", absoluteScore: 60 - i },
    universalSetDesirability: { score: 70 - i, rank: i, rankedSetCount: 135 },

    publicRipContractV8: {
      overallRip: { relativeScore: 90 - i, rank: i, tier: "S", rankedSetCount: 22, status: "ok" },
      financialRip: { relativeScore: 80 - i, rank: i, tier: "A", rankedSetCount: 22 },
      collectorAppeal: { relativeScore: 55 - i, absoluteScore: 40 - i, rank: i, tier: "B", rankedSetCount: 22 },
      audit: { huge: "x".repeat(5000) },
    },
    publicRipContractV10: {
      overallRip: { relativeScore: 90 - i, leaderNormalizedScore: 90 - i, rank: i, tier: "S", rankedSetCount: 22, status: "ok" },
      financialRip: { relativeScore: 80 - i, leaderNormalizedScore: 80 - i, rank: i, tier: "A", rankedSetCount: 22 },
      collectorAppeal: { relativeScore: 55 - i, absoluteScore: 40 - i, rank: i, tier: "B", rankedSetCount: 22 },
      audit: { huge: "v10-audit-must-not-cross".repeat(500) },
    },

    // Never read by the Rankings client.
    openingExperience: { collectorAppeal: { blob: "y".repeat(4000) } },
    financial_rip_v3_payload: { blob: "z".repeat(4000) },
    rip: { score: 1 },
    ripCore: { score: 2 },
    overallRipV6: { score: 3 },
    overallRipV5: { score: 4 },
    rip_core_interpretation: { text: "w".repeat(500) },
    ...overrides,
  };
}

const COHORT = [target(1), target(2), target(3), target(4)];

test("every ranking mode — visible and hidden — reads identically after projection", () => {
  const projected = projectRankingsTargets(COHORT);
  for (const modeId of Object.keys(EXPLORE_RANKING_MODES)) {
    COHORT.forEach((full, i) => {
      const p = projected[i];
      assert.deepEqual(getScoreForMode(p, modeId), getScoreForMode(full, modeId), `${modeId} score`);
      assert.deepEqual(getRankForMode(p, modeId), getRankForMode(full, modeId), `${modeId} rank`);
      assert.deepEqual(getTierForMode(p, modeId), getTierForMode(full, modeId), `${modeId} tier`);
      assert.deepEqual(
        getRankedSetCountForMode(p, modeId),
        getRankedSetCountForMode(full, modeId),
        `${modeId} cohort`
      );
    });
  }
});

test("every sortable column produces the same ordering in both directions", () => {
  const projected = projectRankingsTargets(COHORT);
  for (const columnId of Object.keys(RANKINGS_SORT_COLUMNS)) {
    for (const direction of [SORT_ASC, SORT_DESC]) {
      assert.deepEqual(
        sortRankingsRows(projected, { column: columnId, direction }).map((t) => t.target_id),
        sortRankingsRows(COHORT, { column: columnId, direction }).map((t) => t.target_id),
        `${columnId}/${direction}`
      );
    }
    COHORT.forEach((full, i) => {
      assert.deepEqual(
        readSortValue(projected[i], columnId),
        readSortValue(full, columnId),
        `${columnId} sort value`
      );
    });
  }
});

test("Collector Appeal resolves through the canonical contract after projection", () => {
  const projected = projectRankingsTargets(COHORT);
  COHORT.forEach((full, i) => {
    const block = readCollectorAppealBlock(projected[i]);
    assert.deepEqual(block, readCollectorAppealBlock(full));
    assert.equal(block.available, true, "appeal must not become unavailable");
  });
});

test("Average Loss survives under both spellings", () => {
  const camel = { expectedLossWhenLosing: 7.5, target_id: "c" };
  assert.equal(readAverageLoss(projectRankingsTargets([camel])[0]), 7.5);
  assert.equal(readAverageLoss(projectRankingsTargets([target(1)])[0]), readAverageLoss(target(1)));
});

test("decision-scanner median, break-even aliases, and canonical chase survive projection", () => {
  const source = { median_value: 2.5, modelBreakEvenPrice: 4.25, ripDecision: { topChase: { cardName: "Example", currentMarketPrice: 100, impliedOddsOneInN: 500 } } };
  const [projected] = projectRankingsTargets([source]);
  assert.equal(projected.median_value, 2.5);
  assert.equal(projected.modelBreakEvenPrice, 4.25);
  assert.deepEqual(projected.ripDecision.topChase, source.ripDecision.topChase);
});

test("the heavy blocks the client never reads are dropped, including contract audit", () => {
  const [projected] = projectRankingsTargets([target(1)]);
  for (const heavy of [
    "openingExperience",
    "financial_rip_v3_payload",
    "rip",
    "ripCore",
    "overallRipV6",
    "overallRipV5",
    "rip_core_interpretation",
  ]) {
    assert.equal(heavy in projected, false, `${heavy} still crosses the boundary`);
  }
  assert.equal("audit" in projected.publicRipContractV8, false, "contract audit still shipped");
  assert.equal("overallRip" in projected.publicRipContractV8, true);
  assert.equal("collectorAppeal" in projected.publicRipContractV8, true);
});

test("the projection is materially smaller", () => {
  const before = Buffer.byteLength(JSON.stringify(COHORT));
  const after = Buffer.byteLength(JSON.stringify(projectRankingsTargets(COHORT)));
  assert.ok(after < before / 4, `expected a large reduction, got ${before} -> ${after}`);
});

test("canonical order is preserved", () => {
  assert.deepEqual(
    projectRankingsTargets(COHORT).map((t) => t.target_id),
    COHORT.map((t) => t.target_id)
  );
});

test("a target with no canonical blocks does not gain empty ones", () => {
  const [projected] = projectRankingsTargets([{ target_type: "set", target_id: "bare", name: "Bare" }]);
  assert.equal("overallRipV8" in projected, false);
  assert.equal("publicRipContractV8" in projected, false);
  assert.equal(readCollectorAppealBlock(projected).available, false);
});

test("a non-array input yields an empty leaderboard rather than throwing", () => {
  assert.deepEqual(projectRankingsTargets(null), []);
  assert.deepEqual(projectRankingsTargets(undefined), []);
});

test("packaged V10 survives projection and resolves through the strict headline reader", () => {
  const source = {
    target_id: "v10-contract",
    publicRipContractV10: {
      overallRip: { relativeScore: 8.77, leaderNormalizedScore: 88.77, absoluteScore: 42.1, rank: 2, tier: "S", rankedSetCount: 22, status: "ok" },
      financialRip: { relativeScore: 84.53, rank: 3, tier: "A", rankedSetCount: 22 },
      collectorAppeal: { relativeScore: 74.89, rank: 7, rankedSetCount: 22 },
      audit: { heavy: "must be dropped" },
    },
    setRipV1: { score: 55, rank: 9, cohortSize: 22, familyScores: [] },
  };
  const [projected] = projectRankingsTargets([source]);
  assert.equal("audit" in projected.publicRipContractV10, false);
  assert.deepEqual(projected.publicRipContractV10.overallRip, source.publicRipContractV10.overallRip);
  const headline = readCanonicalOverallRipV10(projected);
  assert.deepEqual(
    { publicScore: headline.publicScore, rank: headline.rank, tier: headline.tier, cohortSize: headline.cohortSize },
    { publicScore: 88.77, rank: 2, tier: "S", cohortSize: 22 },
  );
});

test("top-level V10/V4 fallback survives projection", () => {
  const [projected] = projectRankingsTargets([{
    target_id: "v10-top-level",
    overallRipV10: { relativeScore: 6.42, leaderNormalizedScore: 86.42, rank: 3, tier: "A", cohortSize: 22, status: "ok" },
    financialRipV4: { relativeScore: 2.1, leaderNormalizedScore: 82.1, rank: 4, tier: "A", rankedSetCount: 22, status: "ok" },
  }]);
  assert.equal(projected.financialRipV4.leaderNormalizedScore, 82.1);
  const headline = readCanonicalOverallRipV10(projected);
  assert.deepEqual(
    { publicScore: headline.publicScore, rank: headline.rank, tier: headline.tier, cohortSize: headline.cohortSize },
    { publicScore: 86.42, rank: 3, tier: "A", cohortSize: 22 },
  );
});

test("conflicting V10 and Set RIP V1 remain semantically separated after projection", () => {
  const [projected] = projectRankingsTargets([{
    target_id: "conflict",
    publicRipContractV10: { overallRip: { relativeScore: 2.77, leaderNormalizedScore: 52.77, rank: 14, tier: "D", rankedSetCount: 22 } },
    setRipV1: { score: 77.5, rank: 3, cohortSize: 22, familyScores: [] },
  }]);
  const headline = readCanonicalOverallRipV10(projected);
  assert.deepEqual([headline.rank, (headline.publicScore / 10).toFixed(1), headline.tier], [14, "5.3", "D"]);
  assert.deepEqual([projected.setRipV1.rank, (projected.setRipV1.score / 10).toFixed(1)], [3, "7.8"]);
});

test("the client field manifest advertises current packaged and top-level models", () => {
  for (const path of [
    "publicRipContractV10.overallRip.relativeScore",
    "publicRipContractV10.overallRip.leaderNormalizedScore",
    "publicRipContractV10.overallRip.rank",
    "publicRipContractV10.overallRip.tier",
    "publicRipContractV10.financialRip.relativeScore",
    "publicRipContractV10.collectorAppeal.relativeScore",
    "overallRipV10.relativeScore",
    "overallRipV10.leaderNormalizedScore",
    "financialRipV4.relativeScore",
  ]) assert.ok(RANKINGS_CLIENT_FIELDS.includes(path), path);
});

test("display-only family evidence crosses the lightweight Rankings boundary", () => {
  const displayFamilyScores = [{ family: "enhanced_booster_box", score: 100, rank: 1, cohortSize: 2 }];
  const [projected] = projectRankingsTargets([{ target_id: "enhanced", setRipV1: {
    score: 77.5, familyScores: [], displayFamilyScores,
  } }]);
  assert.deepEqual(projected.setRipV1.displayFamilyScores, displayFamilyScores);
  assert.deepEqual(projected.setRipV1.familyScores, []);
});
