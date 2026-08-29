import assert from "node:assert/strict";
import test from "node:test";
import { buildSealedProductHref } from "../../lib/pokemon/sealedProductRoutes.mjs";
import { normalizeOverallProductResult, sortProductRankingRows } from "./rankingsProductLensModel.mjs";

const result = {
  available: true,
  selectedBudget: { type: "full_market" },
  availableBudgets: [{ type: "full_market", label: "Full Market" }, { type: "fixed", value: 100, label: "$100" }],
  cohortSize: 2,
  rows: [
    { sealedProductId: "p-low", productName: "Alpha Box", overallRipLeaderScore: 71, financialRipLeaderScore: 68, collectorAppealScore: 75 },
    { sealedProductId: "p-high", productName: "Bravo Box", overallRipLeaderScore: 91, financialRipLeaderScore: 88, collectorAppealScore: 90 },
  ],
  authority: { source: "published" },
};

test("top-level Overall Product Rankings populate rows, budgets, sorting, paid fields, and canonical links", () => {
  const normalized = normalizeOverallProductResult(result);
  assert.equal(normalized.rows.length, 2);
  assert.equal(normalized.availableBudgets.length, 2);
  assert.deepEqual(sortProductRankingRows(normalized.rows, "", "overallRipLeaderScore", "desc", true).map((row) => row.sealedProductId), ["p-high", "p-low"]);
  assert.equal(buildSealedProductHref(normalized.rows[0]), "/sealed-products/p-low");
  assert.equal(normalized.rows[0].financialRipLeaderScore, 68);
  assert.equal(normalized.rows[0].collectorAppealScore, 75);
});

test("an invalid successful-looking wrapper cannot become an empty ready table", () => {
  assert.deepEqual(normalizeOverallProductResult({ status: "available", data: result }), {
    available: false, reason: "publication_unavailable", rows: [], availableBudgets: [],
  });
});
