import "../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

import { EXPLORER_SELECTION_ACTIONS, reduceExplorerSelection } from "@/lib/explore/marketExplorerState.mjs";

const raritySelector = fs.readFileSync(new URL("./MarketExplorerRarityMarkets.jsx", import.meta.url), "utf8");
const AVAILABLE = {
  assetKeys: ["raw", "topChase", "sealedMarket"],
  sealedFamilyIds: ["sealed:boosterBox", "sealed:eliteTrainerBox", "sealed:pokemonCenterEliteTrainerBox", "sealed:boosterBundle", "sealed:packs"],
  cardSegmentIds: ["card:raw:specialIllustrationRare", "card:raw:illustrationRare", "card:raw:ultraRare", "card:raw:hyperRare", "card:raw:doubleRare"],
};
const EMPTY = { assetUniverse: [], sealedFamilyIds: [], segmentIds: [] };

test("the accepted rarity selector uses prepared selection, not the retired quick-toggle rail", () => {
  assert.match(raritySelector, /data-rarity-market-trigger/);
  assert.match(raritySelector, /onSelect\(market\.market_key\)/);
  assert.match(raritySelector, /aria-selected=\{active\}/);
  assert.doesNotMatch(raritySelector, /onAddQuery|preflight|Build Market/);
});

test("selection actions are replay-safe", () => {
  for (const [type, seriesId] of [
    [EXPLORER_SELECTION_ACTIONS.toggleCardSegment, "card:raw:illustrationRare"],
    [EXPLORER_SELECTION_ACTIONS.toggleSealedFamily, "sealed:packs"],
    [EXPLORER_SELECTION_ACTIONS.toggleMarket, "raw"],
  ]) {
    const action = { type, seriesId, available: AVAILABLE };
    assert.deepEqual(reduceExplorerSelection(EMPTY, action), reduceExplorerSelection(EMPTY, action));
  }
});

test("a segment selection moves atomically and never adds its parent", () => {
  const next = reduceExplorerSelection(EMPTY, { type: EXPLORER_SELECTION_ACTIONS.toggleCardSegment, seriesId: "card:raw:ultraRare", available: AVAILABLE });
  assert.deepEqual(next.segmentIds, ["card:raw:ultraRare"]);
  assert.deepEqual(next.assetUniverse, []);
  assert.deepEqual(next.sealedFamilyIds, []);
});

test("reconciliation is idempotent", () => {
  const selected = reduceExplorerSelection(EMPTY, { type: EXPLORER_SELECTION_ACTIONS.toggleSealedFamily, seriesId: "sealed:boosterBox", available: AVAILABLE });
  const reconcile = { type: EXPLORER_SELECTION_ACTIONS.reconcile, available: AVAILABLE };
  const first = reduceExplorerSelection(selected, reconcile);
  assert.equal(first, selected);
  assert.equal(reduceExplorerSelection(first, reconcile), first);
});

test("an unknown action leaves the selection untouched", () => {
  assert.equal(reduceExplorerSelection(EMPTY, { type: "nonsense" }), EMPTY);
});
