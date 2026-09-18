import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { canonicalMetricRows, readChaseAccessibilitySetRanking, readFinancialSetRanking, readSetCollectorAppealRanking } from "./setMetricRankingSelectors.mjs";

const table = fs.readFileSync(new URL("./SetMetricRankingsTable.jsx", import.meta.url), "utf8");
const registry = fs.readFileSync(new URL("./setRankingViews.mjs", import.meta.url), "utf8");
const overview = fs.readFileSync(new URL("./RankingsOverviewHighlights.jsx", import.meta.url), "utf8");
const lazy = fs.readFileSync(new URL("./RankingsLazyClient.jsx", import.meta.url), "utf8");

const target = { name: "Authority Set", era: "Era A", median_value: 4.2, modelBreakEvenPrice: 6.5, pack_cost: 10, prob_profit: 0.18, financialRipV4: { leaderNormalizedScore: 81, rank: 8, cohortSize: 22, tier: "A", status: "available", distributionDisclosures: { jackpotValueShare: 0.314 }, depthAndRobustness: { top1EvShare: 0.999 } }, publicCollectorAppealContractV1: { collectorAppeal: { relativeScore: 77, rank: 6, rankedSetCount: 22, tier: "B" }, components: { rosterDesirability: { score: 84 }, desirableOutcomeFrequency: { rawValue: 0.19, displayPercent: 19 } }, drivers: { pokemonAppeal: { publicScore: 91, rank: 2, cohortSize: 22 }, trainerAppeal: { publicScore: 62, rank: 8, cohortSize: 22 }, artistImpact: { publicScore: 55, rank: 10, cohortSize: 22 }, playabilityImpact: { publicScore: 48, rank: 12, cohortSize: 22 } } }, setRipV1: { chaseAccessibility: { publicScore: 72, percent: 4.25, setRank: 9, setCohortSize: 22, chaseDepth: 3, status: "available" } }, rankingsChase: { cardName: "Published Chase", currentMarketPrice: 100, impliedOddsOneInN: 321 } };

test("Financial uses V4 published score/rank and authoritative supporting economics", () => { const row = readFinancialSetRanking(target); assert.deepEqual([row.publicScore, row.rank, row.cohortSize, row.tier], [81, 8, 22, "A"]); assert.deepEqual([row.typicalOpening, row.modelBreakEven, row.modeledReturnPercent, row.chanceToBeatCost], [4.2, 6.5, 65, 0.18]); });
test("Top 1% Value Share reads financialRipV4.distributionDisclosures.jackpotValueShare, never the depthAndRobustness.top1EvShare decoy", () => {
  const row = readFinancialSetRanking(target);
  assert.equal(row.topOneOutcomeValueShare, 0.314);
  assert.notEqual(row.topOneOutcomeValueShare, target.financialRipV4.depthAndRobustness.top1EvShare);
  // A row whose distributionDisclosures is missing but depthAndRobustness carries
  // a top1EvShare value must stay unavailable, not silently substitute the decoy.
  const decoyOnly = { financialRipV4: { leaderNormalizedScore: 50, rank: 1, cohortSize: 5, tier: "A", depthAndRobustness: { top1EvShare: 0.77 } } };
  assert.equal(readFinancialSetRanking(decoyOnly).topOneOutcomeValueShare, null);
});
test("Top 1% Value Share is populated for every row whose disclosure exists (no silent empties)", () => {
  const withDisclosure = { financialRipV4: { leaderNormalizedScore: 1, rank: 1, cohortSize: 2, tier: "C", distributionDisclosures: { jackpotValueShare: 0.42 } } };
  const withoutDisclosure = { financialRipV4: { leaderNormalizedScore: 1, rank: 2, cohortSize: 2, tier: "C", distributionDisclosures: {} } };
  const rows = [withDisclosure, withoutDisclosure].map(readFinancialSetRanking);
  assert.equal(rows[0].topOneOutcomeValueShare, 0.42);
  assert.equal(rows[1].topOneOutcomeValueShare, null);
});
test("Adding Top 1% Value Share does not change canonical financial rank order", () => {
  const a = { name: "A", financialRipV4: { rank: 1, leaderNormalizedScore: 90, tier: "A", distributionDisclosures: {} } };
  const b = { name: "B", financialRipV4: { rank: 2, leaderNormalizedScore: 80, tier: "A", distributionDisclosures: { jackpotValueShare: 0.9 } } };
  const rows = canonicalMetricRows([b, a], readFinancialSetRanking);
  assert.deepEqual(rows.map((t) => t.name), ["A", "B"]);
});
test("Top 1% Value Share is projected from the SAME already-fetched bulk cohort object (no per-row read)", () => {
  assert.match(table, /probability\(metric\.topOneOutcomeValueShare\)/);
  assert.doesNotMatch(table, /fetch\(|await .*top1|N\+1/i);
});
test("Collector reads prepared explanatory drivers without scoring Treatment or Scarcity", () => { const row = readSetCollectorAppealRanking(target); assert.deepEqual([row.publicScore, row.rank, row.cohortSize, row.tier], [77, 6, 22, "B"]); assert.deepEqual([row.pokemonAppeal.publicScore, row.trainerAppeal.publicScore, row.artistImpact.publicScore, row.playabilityImpact.publicScore], [91, 62, 55, 48]); for (const forbidden of ["Treatment Score", "Scarcity Score"]) assert.ok(!table.includes(forbidden)); });
test("Chase uses Set authority, published rank, and published chase odds", () => { const row = readChaseAccessibilitySetRanking(target); assert.deepEqual([row.publicScore, row.rank, row.cohortSize, row.chaseDepth], [72, 9, 22, 3]); assert.deepEqual([row.chase.name, row.chase.oneInPacks], ["Published Chase", 321]); assert.ok(!table.includes("currentMarketPrice /")); });
test("Era filtering preserves global canonical rank", () => { const other = { ...target, name: "Other", era: "Era B", financialRipV4: { ...target.financialRipV4, rank: 1 } }; const rows = canonicalMetricRows([other, target], readFinancialSetRanking, "Era A"); assert.equal(rows.length, 1); assert.equal(readFinancialSetRanking(rows[0]).rank, 8); });
test("missing headline values stay unavailable rather than zero", () => { assert.equal(readFinancialSetRanking({ financialRipV4: { leaderNormalizedScore: null } }).publicScore, null); assert.equal(readSetCollectorAppealRanking({}).publicScore, null); assert.equal(readChaseAccessibilitySetRanking({ setRipV1: { chaseAccessibility: { publicScore: null } } }).publicScore, null); });
test("registry makes four views Plus while RIP and Pack Economics remain public/mixed", () => { assert.equal((registry.match(/requiredPlan: INDEX_PLAN_PLUS/g) || []).length, 4); assert.match(registry, /ripScore[^\n]+requiredPlan: null/); assert.match(registry, /packEconomics[^\n]+requiredPlan: null/); });
test("Overview remains public-only and no per-tab Set endpoint exists", () => { for (const paid of ["Financial RIP", "Collector Appeal", "Chase Accessibility", "familyScores"]) assert.ok(!overview.includes(paid)); assert.equal((lazy.match(/lens\?lens=sets/g) || []).length, 1); for (const endpoint of ["lens=financial", "lens=collector", "lens=chase"]) assert.ok(!lazy.includes(endpoint)); });
test("dedicated tables distinguish component semantics and render a truthful empty-filter state", () => { for (const label of ["Pokémon Appeal", "Trainer Appeal", "Artist Impact", "Playability Impact"]) assert.ok(table.includes(label)); assert.ok(table.includes("No ranked sets match the current filters.")); });
