import test from "node:test";
import assert from "node:assert/strict";

import {
  MARKET_EXPLORER_SCREENS,
  MARKET_EXPLORER_QUICK_PRESETS,
  canUseScreen,
  draftForQuickPreset,
  resolveScreenResults,
  validateScreenRegistry,
} from "./marketExplorerScreens.mjs";

test("the V1 Screen registry is valid, unique, and deterministically entitled", () => {
  assert.equal(validateScreenRegistry(), true);
  assert.equal(new Set(MARKET_EXPLORER_SCREENS.map((screen) => screen.id)).size, MARKET_EXPLORER_SCREENS.length);
  const plus = MARKET_EXPLORER_SCREENS.find((screen) => screen.id === "rarity-leaders");
  assert.equal(canUseScreen(plus, null), false);
  assert.equal(canUseScreen(plus, "plus"), true);
  assert.equal(canUseScreen(plus, "premium"), true);
  assert.ok(MARKET_EXPLORER_SCREENS.every((screen) => canUseScreen(screen, "plus")));
});

test("momentum and drawdown rankings use canonical prepared series and stable tie breaks", () => {
  const prepared = [
    { key: "b", group: "card", changes: { "30D": { percent: 8 } }, trend: [{ value: 100 }, { value: 75 }] },
    { key: "a", group: "card", changes: { "30D": { percent: 8 } }, trend: [{ value: 100 }, { value: 80 }] },
    { key: "parent", isParent: true, changes: { "30D": { percent: 99 } }, trend: [{ value: 1 }, { value: 1 }] },
  ];
  const momentum = MARKET_EXPLORER_SCREENS.find((screen) => screen.id === "momentum-leaders");
  const drawdowns = MARKET_EXPLORER_SCREENS.find((screen) => screen.id === "largest-drawdowns");
  assert.deepEqual(resolveScreenResults(momentum, prepared).map((row) => row.series.key), ["a", "b"]);
  const rows = resolveScreenResults(drawdowns, prepared);
  assert.deepEqual(rows.map((row) => row.series.key), ["b", "a"]);
  assert.equal(rows[0].value, -25);
  assert.ok(Math.abs(rows[1].value + 20) < 1e-9);
});

test("only Quick Presets produce serializable builder definitions", () => {
  const price = MARKET_EXPLORER_QUICK_PRESETS.find((screen) => screen.id === "premium-market");
  const clean = draftForQuickPreset(price, { asset: "sealed", segmentIds: ["boosterBox"], pokemonIds: ["149"] });
  assert.deepEqual(clean.priceSegmentIds, ["premium"]);
  assert.deepEqual(clean.segmentIds, []);
  assert.deepEqual(clean.pokemonIds, []);
});

test("selected-set Top 10 is contextual analysis, never a Quick Market template", () => {
  assert.equal(MARKET_EXPLORER_QUICK_PRESETS.some((entry) => entry.id === "set-top-ten"), false);
});

test("ordinary templates preserve multi-scope and Prompt-1 explicit membership", () => {
  const screen = MARKET_EXPLORER_QUICK_PRESETS.find((entry) => entry.id === "obtainable-market");
  const draft = draftForQuickPreset(screen, {
    asset: "cards", eraIds: ["era-a", "era-b"], setIds: ["set-a", "set-b"],
    membershipMode: "explicit", instrumentIds: ["variant-a", "variant-b"],
  });
  assert.deepEqual(draft.eraIds, ["era-a", "era-b"]);
  assert.deepEqual(draft.setIds, ["set-a", "set-b"]);
  assert.equal(draft.membershipMode, "explicit");
  assert.deepEqual(draft.instrumentIds, ["variant-a", "variant-b"]);
});

test("Screens are discovery-only and legacy templates exclude contextual ranking", () => {
  assert.ok(MARKET_EXPLORER_SCREENS.every((screen) => screen.type !== "builderTemplate"));
  assert.equal(MARKET_EXPLORER_QUICK_PRESETS.length, 5);
  assert.ok(MARKET_EXPLORER_QUICK_PRESETS.every((preset) => preset.type === "builderTemplate"));
});
