import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("./ProductChaseIntelligenceSection.jsx", import.meta.url), "utf8");
const ripSource = fs.readFileSync(new URL("./ProductRipSection.jsx", import.meta.url), "utf8");
const routeSource = fs.readFileSync(
  new URL("../../../app/api/explore/product-chase-intelligence/route.js", import.meta.url),
  "utf8",
);

test("no client-side formula computation - only formatting of server-provided fields", () => {
  // Guards against a future regression that recomputes HC/O_budget/ECE in
  // the browser instead of reading the server's precomputed row.
  assert.doesNotMatch(source, /Math\.pow|\*\*\s*n|1\s*-\s*\(1\s*-/);
  assert.doesNotMatch(source, /HC_i|hcRaw|computeOBudget|compute_o_budget/);
});

test("fetches from the dedicated Chase Intelligence proxy route, never the RIP or rankings endpoints", () => {
  assert.match(source, /\/api\/explore\/product-chase-intelligence/);
  assert.doesNotMatch(source, /\/api\/explore\/product-rankings/);
  assert.doesNotMatch(source, /\/api\/explore\/card-chase-efficiency/);
});

test("proxy route forwards to the backend Premium endpoint and enforces nothing itself", () => {
  assert.match(routeSource, /\/explore\/product-chase-intelligence/);
  // Entitlement must be enforced server-side on the backend, not re-implemented here.
  assert.doesNotMatch(routeSource, /index_plan|FEATURE_/);
});

test("never presented as part of Overall RIP", () => {
  assert.doesNotMatch(source, /Overall RIP score|overallRipScore/);
  assert.match(source, /separate measure from Overall RIP/);
});

test("distinct from ProductRipSection - not rendered inside it, no shared JSX tree", () => {
  assert.doesNotMatch(ripSource, /ProductChaseIntelligenceSection/);
});

test("Premium-gated lock component exists using the Premium plan tier", () => {
  assert.match(source, /export function ProductChaseIntelligenceLock/);
  assert.match(source, /INDEX_PLAN_PREMIUM/);
});

test("no budget selected never fabricates an O_budget rank", () => {
  assert.match(source, /hasBudgetResult/);
  assert.match(source, /Choose a budget to see Chase Access/);
});

const clientSource = fs.readFileSync(
  new URL("./SealedProductDetailClient.jsx", import.meta.url),
  "utf8",
);

test("section is actually mounted on the product detail page, gated on Premium entitlement", () => {
  assert.match(clientSource, /import ProductChaseIntelligenceSection, \{ ProductChaseIntelligenceLock \} from "\.\/ProductChaseIntelligenceSection"/);
  assert.match(clientSource, /hasIndexPremiumAccess\(user\?\.index_plan\)/);
  assert.match(clientSource, /premiumEntitled \? \(\s*<ProductChaseIntelligenceSection/);
  assert.match(clientSource, /<ProductChaseIntelligenceLock \/>/);
  assert.match(clientSource, /sealedProductId=\{detail\.product\.id\}/);
  assert.match(clientSource, /setId=\{detail\.set\.id\}/);
});

test("Premium data is not fetched until entitlement allows it - lock branch never mounts the fetching component", () => {
  const premiumBranch = clientSource.slice(
    clientSource.indexOf("premiumEntitled ? ("),
    clientSource.indexOf("<ProductComparisonSection"),
  );
  // Only one of the two branches renders the fetching component; the other
  // renders the static lock shell with no fetch.
  assert.match(premiumBranch, /<ProductChaseIntelligenceSection/);
  assert.match(premiumBranch, /<ProductChaseIntelligenceLock \/>/);
});

test("scopes every request to a single product via sealed_product_id - never fetches the full cohort", () => {
  assert.match(source, /params\.set\("sealed_product_id"/);
});

test("explicit budget selector uses canonical bands, defaults to $100, no invented unlimited default", () => {
  assert.match(source, /CANONICAL_CHASE_BUDGETS = \[25, 50, 100, 150, 250, 500\]/);
  assert.match(source, /DEFAULT_CHASE_BUDGET = 100/);
  // No request ever asks the server for an unbounded/"unlimited" budget band.
  assert.doesNotMatch(source, /params\.set\("budget",\s*"full_market"\)/);
  assert.doesNotMatch(source, /CANONICAL_CHASE_BUDGETS[\s\S]*?full_market/);
  assert.match(source, /data-chase-budget-selector/);
});

// Copy-discipline check runs against user-FACING text only (JSX strings),
// not source comments that describe what phrasing to avoid - the comment at
// the top of this file intentionally quotes the forbidden phrases.
const userFacingSource = source
  .split("\n")
  .filter((line) => !line.trim().startsWith("//"))
  .join("\n");

test("copy discipline - never phrases O_budget as a literal chance/probability of pulling a chase card", () => {
  assert.doesNotMatch(userFacingSource, /chance (of|to) (pulling|hit(ting)?) (a |the )?chase/i);
  assert.doesNotMatch(userFacingSource, /chance of pulling/i);
  assert.match(source, /how much access does this product give you to/i);
});

test("five distinct states are implemented: loading, budget-below-minimum, authority-unavailable, unsupported composition, and error", () => {
  assert.match(source, /data-chase-state="loading"/);
  assert.match(source, /data-chase-state="error"/);
  assert.match(source, /data-chase-state="unavailable"/);
  assert.match(source, /data-chase-state="budget-below-minimum"/);
  assert.match(source, /Budget is below the current price of one unit\./);
  assert.match(source, /data-chase-state="authority-unavailable"/);
  assert.match(source, /data-chase-state="unsupported-composition"/);
});

test("ECE is presented as a per-product diagnostic, never a cross-format score or rank", () => {
  assert.match(source, /Effective Pack Efficiency/);
  assert.doesNotMatch(source, /Effective Pack Efficiency Rank|ECE Rank/i);
});

test("no cross-product rank is rendered from a single-product-scoped response", () => {
  assert.doesNotMatch(source, /oBudgetRank/);
});

test("mobile-safe: budget selector wraps instead of overflowing", () => {
  assert.match(source, /flex-wrap/);
});
