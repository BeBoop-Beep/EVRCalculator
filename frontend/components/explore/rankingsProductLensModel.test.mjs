import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { buildSealedProductHref } from "../../lib/pokemon/sealedProductRoutes.mjs";
import {
  defaultProductSortDirection,
  normalizeOverallProductResult,
  sortProductRankingRows,
} from "./rankingsProductLensModel.mjs";

const productClientSource = fs.readFileSync(new URL("./RankingsProductLensClient.jsx", import.meta.url), "utf8");

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

// Chase Accessibility is SET-level; `chaseAccessibilityValue` reads the
// nested backend authority block (row.chaseAccessibility.value), not a flat
// field, and an unavailable row (null block) sorts last — never coerced to
// zero. This is the sort key `RankingsProductLensClient.jsx` wires to its
// visible "Sort products" menu (a real, user-reachable control, unlike the
// hidden Set Rankings ranking-mode dropdown).
test("chaseAccessibilityValue sorts by the nested set-level authority block and puts unavailable last", () => {
  const rows = [
    { sealedProductId: "p-mid", chaseAccessibility: { value: 0.05 } },
    { sealedProductId: "p-high", chaseAccessibility: { value: 0.2 } },
    { sealedProductId: "p-none", chaseAccessibility: null },
  ];
  assert.deepEqual(
    sortProductRankingRows(rows, "", "chaseAccessibilityValue", "desc", false).map((row) => row.sealedProductId),
    ["p-high", "p-mid", "p-none"]
  );
  assert.deepEqual(
    sortProductRankingRows(rows, "", "chaseAccessibilityValue", "asc", false).map((row) => row.sealedProductId),
    ["p-mid", "p-high", "p-none"]
  );
});

test("Closest to #1 defaults ascending and sorts leader then smallest required discount", () => {
  const rows = [
    { sealedProductId: "far", budgetRank: 8, bestOpenPriceStatus: "resolved_below_market", bestOpenPriceGapPercent: 0.2031 },
    { sealedProductId: "leader", budgetRank: 1, bestOpenPriceStatus: "current_number_one_with_headroom", bestOpenPriceGapPercent: -0.1299 },
    { sealedProductId: "closest", budgetRank: 2, bestOpenPriceStatus: "resolved_below_market", bestOpenPriceGapPercent: 0.092 },
    { sealedProductId: "next", budgetRank: 3, bestOpenPriceStatus: "resolved_below_market", bestOpenPriceGapPercent: 0.124 },
    { sealedProductId: "unavailable", budgetRank: 99, bestOpenPriceStatus: null, bestOpenPriceGapPercent: null },
  ];
  assert.equal(defaultProductSortDirection("bestOpenPriceGapPercent"), "asc");
  assert.deepEqual(
    sortProductRankingRows(rows, "", "bestOpenPriceGapPercent", "asc", true).map((row) => row.sealedProductId),
    ["leader", "closest", "next", "far", "unavailable"],
  );
});

test("Closest to #1 can be reversed without coercing unavailable rows to zero", () => {
  const rows = [
    { sealedProductId: "leader", bestOpenPriceStatus: "current_number_one_with_headroom", bestOpenPriceGapPercent: -0.1 },
    { sealedProductId: "near", bestOpenPriceStatus: "resolved_below_market", bestOpenPriceGapPercent: 0.1 },
    { sealedProductId: "far", bestOpenPriceStatus: "resolved_below_market", bestOpenPriceGapPercent: 0.5 },
    { sealedProductId: "none", bestOpenPriceGapPercent: null },
  ];
  assert.deepEqual(
    sortProductRankingRows(rows, "", "bestOpenPriceGapPercent", "desc", true).map((row) => row.sealedProductId),
    ["far", "near", "leader", "none"],
  );
});

test("Budget Products UI consumes backend generic fields without V10 authority logic", () => {
  assert.match(productClientSource, /row\?\.budgetRank/);
  assert.match(productClientSource, /row\?\.overallRipLeaderScore/);
  assert.doesNotMatch(productClientSource, /rankedUnderV12Authority/);
  assert.match(productClientSource, /<table/);
  assert.match(productClientSource, /row\.chaseAccessibility\.publicScore/);
  assert.match(productClientSource, /row\.chaseAccessibility\.setRank/);
});

test("equal Chase Accessibility scores preserve backend rank order", () => {
  const rows = [
    { sealedProductId: "rank-2", budgetRank: 2, chaseAccessibility: { value: 0.2 } },
    { sealedProductId: "rank-5", budgetRank: 5, chaseAccessibility: { value: 0.2 } },
  ];
  assert.deepEqual(
    sortProductRankingRows(rows, "", "chaseAccessibilityValue", "desc", true)
      .map((row) => row.sealedProductId),
    ["rank-2", "rank-5"],
  );
});

test("an invalid successful-looking wrapper cannot become an empty ready table", () => {
  assert.deepEqual(normalizeOverallProductResult({ status: "available", data: result }), {
    available: false, reason: "publication_unavailable", rows: [], availableBudgets: [],
  });
});

test("unavailable Best-Open sorting falls back to ordinary ranking without hiding rows", async () => {
  const {resolveProductSort}=await import("./rankingsProductLensModel.mjs");
  assert.deepEqual(resolveProductSort("bestOpenPriceGapPercent","asc",false,true),{key:"overallRipLeaderScore",direction:"desc"});
  assert.deepEqual(resolveProductSort("bestOpenPriceGapPercent","asc",true,true),{key:"bestOpenPriceGapPercent",direction:"asc"});
});
