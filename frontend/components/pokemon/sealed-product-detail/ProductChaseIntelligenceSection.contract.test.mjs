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
