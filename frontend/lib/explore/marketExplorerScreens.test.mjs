import test from "node:test";
import assert from "node:assert/strict";

import {
  MARKET_EXPLORER_SCREENS,
  canUseScreen,
  draftForScreenResult,
  resolveScreenResults,
  validateScreenRegistry,
} from "./marketExplorerScreens.mjs";

test("the V1 Screen registry is valid, unique, and deterministically entitled", () => {
  assert.equal(validateScreenRegistry(), true);
  assert.equal(new Set(MARKET_EXPLORER_SCREENS.map((screen) => screen.id)).size, MARKET_EXPLORER_SCREENS.length);
  const plus = MARKET_EXPLORER_SCREENS.find((screen) => screen.id === "rarity-leaders");
  const premium = MARKET_EXPLORER_SCREENS.find((screen) => screen.id === "set-top-ten");
  assert.equal(canUseScreen(plus, null), false);
  assert.equal(canUseScreen(plus, "plus"), true);
  assert.equal(canUseScreen(plus, "premium"), true);
  assert.equal(canUseScreen(premium, "plus"), false);
  assert.equal(canUseScreen(premium, "premium"), true);
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

test("Screen handoff produces the same serializable builder definition", () => {
  const rarity = MARKET_EXPLORER_SCREENS.find((screen) => screen.id === "rarity-leaders");
  const draft = draftForScreenResult(rarity, { series: { group: "card", backendKey: "specialIllustrationRare" } });
  assert.deepEqual(draft, { asset: "cards", segmentIds: ["specialIllustrationRare"], mode: "all" });

  const price = MARKET_EXPLORER_SCREENS.find((screen) => screen.id === "premium-market");
  const clean = draftForScreenResult(price, null, { asset: "sealed", segmentIds: ["boosterBox"], pokemonIds: ["149"] });
  assert.deepEqual(clean.priceSegmentIds, ["premium"]);
  assert.deepEqual(clean.segmentIds, []);
  assert.deepEqual(clean.pokemonIds, []);
});

test("selected-set Top 10 retains only scope before applying point-in-time ranking", () => {
  const screen = MARKET_EXPLORER_SCREENS.find((entry) => entry.id === "set-top-ten");
  const draft = draftForScreenResult(screen, null, { asset: "cards", eraIds: ["sv"], setIds: ["sv8"], pokemonIds: ["149"] });
  assert.deepEqual(draft.setIds, ["sv8"]);
  assert.deepEqual(draft.pokemonIds, []);
  assert.equal(draft.mode, "chase");
  assert.equal(draft.topN, 10);
});
