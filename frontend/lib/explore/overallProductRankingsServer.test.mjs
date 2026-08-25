import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { normalizeOverallProductRankings } from "./overallProductRankingsNormalizer.mjs";

test("dedicated Overall reader preserves one published cohort", () => {
  const payload = { available: true, cohortSize: 1, selectedBudget: { type: "full_market", value: 1350 }, rows: [{ budgetRank: 1, expectedValue: 900 }] };
  assert.deepEqual(normalizeOverallProductRankings(payload), { status: "available", reason: null, data: payload });
});

test("dedicated Overall reader distinguishes unavailable from loading", () => {
  assert.deepEqual(normalizeOverallProductRankings({ available: false, reason: "stale_budget_authority", rows: [] }), { status: "unavailable", reason: "stale_budget_authority", data: null });
});

test("dedicated Overall reader accepts every expanded canonical budget", () => {
  const source = fs.readFileSync(path.resolve("lib/explore/overallProductRankingsServer.js"), "utf8");
  for (const budget of ["25", "50", "100", "150", "250", "500", "750", "1000", "1250"]) {
    assert.ok(source.includes(`"${budget}"`), budget);
  }
  assert.ok(source.includes('"full_market"'));
});
