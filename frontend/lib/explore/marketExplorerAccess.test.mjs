import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {
  ACTIVE_MARKET_LIMIT_COPY,
  FOCUS_TOOL_STATE,
  MARKET_EXPLORER_ACTIVE_MARKET_LIMIT,
  NO_BACKEND_CAPABILITIES,
  activeMarketLimitFor,
  countActiveMarkets,
  evaluateActiveMarketAdd,
  resolveFocusToolStates,
  resolveMarketExplorerCapabilities,
} from "./marketExplorerAccess.mjs";

test("commercial limits are centralised: Basic 1, Index+ 3, Premium 10", () => {
  assert.deepEqual({ ...MARKET_EXPLORER_ACTIVE_MARKET_LIMIT }, { basic: 1, plus: 3, premium: 10 });
  assert.equal(activeMarketLimitFor(null), 1);
  assert.equal(activeMarketLimitFor("plus"), 3);
  assert.equal(activeMarketLimitFor("premium"), 10);
  assert.equal(activeMarketLimitFor("garbage"), 1);
});

test("adding beyond the limit is refused with the exact plan copy; nothing is replaced", () => {
  assert.equal(evaluateActiveMarketAdd("plus", 2).allowed, true);
  const plusFull = evaluateActiveMarketAdd("plus", 3);
  assert.equal(plusFull.allowed, false);
  assert.equal(plusFull.message, "Index+ supports up to 3 active comparison markets.");
  assert.equal(plusFull.upgrade, true);
  assert.equal(evaluateActiveMarketAdd("premium", 9).allowed, true);
  const premiumFull = evaluateActiveMarketAdd("premium", 10);
  assert.equal(premiumFull.allowed, false);
  assert.equal(premiumFull.message, "Premium supports up to 10 active comparison markets.");
  assert.equal(premiumFull.upgrade, false, "Premium is the top tier");
  const basicFull = evaluateActiveMarketAdd(null, 1);
  assert.equal(basicFull.allowed, false);
  assert.equal(basicFull.message, ACTIVE_MARKET_LIMIT_COPY.basic);
  assert.match(basicFull.message, /Index\+ supports up to 3/);
});

test("hidden markets and loading requests count; focus is not a market", () => {
  // Hidden keys are still ACTIVE keys, so they occupy a slot.
  assert.equal(countActiveMarkets({ activeKeys: ["a", "b", "c"], pendingKeys: [] }), 3);
  assert.equal(countActiveMarkets({ activeKeys: ["a", "b"], pendingKeys: ["c"] }), 3);
  assert.equal(countActiveMarkets({ activeKeys: ["a"], pendingKeys: ["a"] }), 1, "a key is never double counted");
  // The counter has no focus input at all: focus cannot change occupancy.
  assert.equal(countActiveMarkets.length <= 1, true);
});

test("Demand Pressure states: locked (Basic) / unavailable (Index+, Premium) / available only when published", () => {
  assert.equal(resolveFocusToolStates(null, "m").demandPressure.state, FOCUS_TOOL_STATE.locked);
  assert.match(resolveFocusToolStates(null, "m").demandPressure.reason, /Index\+/);
  for (const plan of ["plus", "premium"]) {
    const dp = resolveFocusToolStates(plan, "m").demandPressure;
    assert.equal(dp.state, FOCUS_TOOL_STATE.unavailable);
    assert.equal(dp.reason, "Demand Pressure data is not available for this market yet.");
  }
  const published = { demandPressure: { m: { available: true } }, fairValue: {} };
  assert.equal(resolveFocusToolStates("plus", "m", published).demandPressure.state, FOCUS_TOOL_STATE.available);
  // Only EXPLICIT availability counts, and only for that market.
  assert.equal(resolveFocusToolStates("plus", "other", published).demandPressure.state, FOCUS_TOOL_STATE.unavailable);
  assert.equal(resolveFocusToolStates("plus", "m", { demandPressure: { m: { available: "yes" } } }).demandPressure.state, FOCUS_TOOL_STATE.unavailable);
  // Entitlement still wins over a published capability.
  assert.equal(resolveFocusToolStates(null, "m", published).demandPressure.state, FOCUS_TOOL_STATE.locked);
});

test("Fair Value states: locked (Basic and Index+) / unavailable (Premium) / available only when published", () => {
  assert.equal(resolveFocusToolStates(null, "m").fairValue.state, FOCUS_TOOL_STATE.locked);
  assert.equal(resolveFocusToolStates("plus", "m").fairValue.state, FOCUS_TOOL_STATE.locked);
  assert.equal(resolveFocusToolStates("premium", "m").fairValue.state, FOCUS_TOOL_STATE.unavailable);
  const published = { fairValue: { m: { available: true, values: [1, 2] } } };
  assert.equal(resolveFocusToolStates("premium", "m", published).fairValue.state, FOCUS_TOOL_STATE.available);
  assert.equal(resolveFocusToolStates("plus", "m", published).fairValue.state, FOCUS_TOOL_STATE.locked);
  assert.deepEqual(NO_BACKEND_CAPABILITIES.fairValue, {});
});

test("capability map exposes entitlement and limit for each tier", () => {
  assert.deepEqual(resolveMarketExplorerCapabilities(null), { tier: "basic", activeMarketLimit: 1, canUseDemandPressure: false, canUseFairValue: false });
  assert.deepEqual(resolveMarketExplorerCapabilities("plus"), { tier: "plus", activeMarketLimit: 3, canUseDemandPressure: true, canUseFairValue: false });
  assert.deepEqual(resolveMarketExplorerCapabilities("premium"), { tier: "premium", activeMarketLimit: 10, canUseDemandPressure: true, canUseFairValue: true });
});

test("Explorer components never compare plan strings or carry a limit literal", () => {
  const dir = path.resolve(process.cwd(), "components/explore");
  const files = ["MarketExplorerClient.jsx", "MarketExplorerFocusTools.jsx", "MarketExplorerActiveMarkets.jsx", "MarketExplorerBrowse.jsx"];
  for (const file of files) {
    const source = fs.readFileSync(path.join(dir, file), "utf8");
    assert.doesNotMatch(source, /(?:plan|accessMode|indexPlan)\s*===?\s*["'](?:premium|plus|basic)["']/, `${file} compares a plan string`);
    assert.doesNotMatch(source, /(?:limit|LIMIT)\s*[<>=]+\s*(?:3|10)\b/, `${file} hard-codes a market limit`);
  }
});
