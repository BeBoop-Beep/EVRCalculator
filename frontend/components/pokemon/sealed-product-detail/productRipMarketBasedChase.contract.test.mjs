// Product RIP — Market-Based Opening Quality / Chase Accessibility wiring
// contract tests (V12 Product RIP UI standardization pass, Phase 17 I-Q).
//
// Follows the SAME source-text testing pattern already established by
// `SealedProductDetail.contract.test.mjs` for this component family (that
// file's own header explains why: this component tree pulls in Next path
// aliases that don't resolve outside a Next build).

import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8");
const rip = read("./ProductRipSection.jsx");
const comparisons = fs.existsSync(new URL("./ProductComparisonSection.jsx", import.meta.url))
  ? read("./ProductComparisonSection.jsx")
  : "";
const chaseIntelligence = read("./ProductChaseIntelligenceSection.jsx");

test("I: Product RIP contains Overall RIP, Market-Based Opening Quality, Financial RIP, Chase Accessibility and Collector Appeal", () => {
  assert.match(rip, /Overall RIP/);
  assert.match(rip, /MARKET_BASED_LABEL/);
  assert.match(rip, /Financial RIP/);
  assert.match(rip, /Chase Accessibility/);
  assert.match(rip, /Collector Appeal/);
});

test("J: Financial RIP and Chase Accessibility are grouped under the Market-Based Opening Quality section", () => {
  const marketSectionMatch = rip.match(
    /data-market-based-opening-quality="compact"[\s\S]*?<\/section>/,
  );
  assert.ok(marketSectionMatch, "expected a data-market-based-opening-quality section");
  const marketSection = marketSectionMatch[0];
  assert.match(marketSection, /Financial RIP/);
  assert.match(marketSection, /ChaseAccessibilityCard/);
  assert.doesNotMatch(marketSection, /Collector Appeal/);
});

test("K: Market-Based Opening Quality itself carries no independent score/rank/tier", () => {
  const marketSectionMatch = rip.match(
    /data-market-based-opening-quality="compact"[\s\S]*?<\/section>/,
  );
  const marketSection = marketSectionMatch[0];
  // No standalone "Market-Based score" value is ever rendered - only the two
  // real child metrics (Financial RIP's own score, Chase's own raw metric).
  assert.doesNotMatch(marketSection, /Market-Based Opening Quality Score/i);
  assert.match(marketSection, /MARKET_BASED_EXPLANATORY_NOTE/);
});

test("L: Chase Accessibility never fabricates a rank/tier/cohortSize", () => {
  assert.doesNotMatch(rip, /chase\.rank/);
  assert.doesNotMatch(rip, /chase\.tier/);
  assert.doesNotMatch(rip, /chase\.cohortSize/);
  assert.match(rip, /selectChaseAccessibilityPresentation/);
});

test("M: set-level inheritance copy is present for Chase Accessibility and Collector Appeal, product-specific for Financial RIP", () => {
  assert.match(rip, /This product/);
  const chaseCount = (rip.match(/Parent set/g) || []).length;
  assert.ok(chaseCount >= 2, "expected 'Parent set' labeling on both Chase Accessibility and Collector Appeal");
});

test("N: no model-weight percentages are ever rendered on this surface", () => {
  for (const forbidden of ["86%", "10%", "90%", "95.56%", "4.44%", "0.04", "0.86"]) {
    assert.equal(rip.includes(forbidden), false, `forbidden weight literal "${forbidden}" found in ProductRipSection.jsx`);
  }
  // "4%" alone is too broad a literal (it also matches unrelated CSS like
  // `color-mix(...,14%,...)`) - assert instead that no weight-disclosure
  // SENTENCE shape appears.
  assert.doesNotMatch(rip, /\d{1,3}%\s*(Financial|Chase|Collector)/i);
  assert.doesNotMatch(rip, /Financial \+ .*Chase/i);
});

test("O: Product Chase Intelligence remains a separate section/contract, never merged into Product RIP", () => {
  assert.doesNotMatch(rip, /O_budget|oBudget|Chase Access at/);
  assert.doesNotMatch(rip, /ProductChaseIntelligenceSection/);
  assert.match(chaseIntelligence, /Product Chase Intelligence|Chase Access/);
});

test("P: the Chase Accessibility presentation never claims a scored weight/contribution", () => {
  assert.doesNotMatch(rip, /transformK|A_score|saturating/);
  assert.match(rip, /Context — not an additional scoring input/);
});

test("Q: the UI-2 'Cohort rank not yet available' inconsistency does not exist in this surface either", () => {
  assert.doesNotMatch(rip, /Cohort rank not yet available/);
});

test("Product RIP Chase Accessibility never renders Premium Product Chase fields", () => {
  for (const forbidden of ["ece", "eceVersion", "effectivePacks", "oBudgetRank", "quantity"]) {
    assert.equal(rip.includes(forbidden), false, `forbidden Premium Product Chase field "${forbidden}" found`);
  }
});
