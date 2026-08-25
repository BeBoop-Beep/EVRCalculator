import assert from "node:assert/strict";
import test from "node:test";
import { normalizeOverallProductRankings } from "./overallProductRankingsNormalizer.mjs";

test("dedicated Overall reader preserves one published cohort", () => {
  const payload = { available: true, cohortSize: 1, selectedBudget: { type: "full_market", value: 1350 }, rows: [{ budgetRank: 1, expectedValue: 900 }] };
  assert.deepEqual(normalizeOverallProductRankings(payload), { status: "available", reason: null, data: payload });
});

test("dedicated Overall reader distinguishes unavailable from loading", () => {
  assert.deepEqual(normalizeOverallProductRankings({ available: false, reason: "stale_budget_authority", rows: [] }), { status: "unavailable", reason: "stale_budget_authority", data: null });
});
