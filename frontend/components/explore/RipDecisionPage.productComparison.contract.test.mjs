import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const source = fs.readFileSync(path.resolve("components/explore/RipDecisionPage.jsx"), "utf8");
const primitives = fs.readFileSync(path.resolve("components/explore/RankedProductTablePrimitives.jsx"), "utf8");
const comparison = source.slice(source.indexOf('data-rip-section="compare-products"'), source.indexOf('data-rip-section="chase-summary"'));

test("Set Product Comparison locks the approved nine-column contract", () => {
  const head = comparison.slice(comparison.indexOf("<thead"), comparison.indexOf("</thead>"));
  const compactHead = head.replace(/\s+/g, " ");
  const labels = ["Product Rank", ">Product</th>", "RIP Score", "Tier", "Market Price", "$ / Pack", "Typical Back", "Entertainment Cost", "Recover Cost"];
  let previous = -1;
  for (const label of labels) { const current = compactHead.indexOf(label); assert.ok(current > previous, label); previous = current; }
  assert.equal((head.match(/<th scope="col"/g) || []).length, 9);
  assert.ok(!comparison.includes("Family Rank"));
  assert.ok(!comparison.includes("Overall Rank"));
  assert.ok(!comparison.includes("Opening Budget"));
  assert.ok(!comparison.includes("comparisonFamilyRow"));
});

test("Set Product Comparison reuses canonical Rankings presentation and access primitives", () => {
  for (const token of ["RipScoreBadge", "RipTierMark", "PublicRipTierInfo", "PremiumMetricLock", "RankedProductIdentity", "RankedProductHeader", "useRankingsAccess"]) assert.ok(source.includes(token), token);
  assert.ok(source.includes("canViewRankingsIntelligence: canViewProductRipIntelligence"));
  assert.ok(source.includes("familyRankInfo?.overallRipLeaderScore"));
  assert.ok(source.includes("familyRankInfo?.publicTier"));
  assert.ok(source.includes("#${familyRankInfo.familyRank} / ${familyRankInfo.familySize}"));
  assert.ok(primitives.includes('product?.productFamily === "loose_booster_pack"'));
});

test("Set economics remain sourced from the existing normalized product contract", () => {
  for (const token of ["product.marketPrice", "product.packCount", "product.typicalOpening", "product.entertainmentCost.perPack", "product.chanceToRecoverCost"]) assert.ok(source.includes(token), token);
  assert.ok(comparison.includes("Market Price"));
  assert.ok(comparison.includes("$ / Pack"));
  assert.ok(comparison.includes("Typical Back"));
  assert.ok(comparison.includes("Entertainment Cost"));
  assert.ok(comparison.includes("Recover Cost"));
});

test("mobile keeps public identity and market price while locking all analytical rows", () => {
  assert.ok(comparison.includes("data-set-product-comparison-mobile"));
  assert.ok(source.includes("min-w-0 w-full overflow-hidden p-3"));
  assert.ok(source.includes("<ProductIdentity"));
  assert.ok(source.includes("<LockedValue canView={canView}"));
  assert.ok(source.includes("{money(product.marketPrice)}"));
});
