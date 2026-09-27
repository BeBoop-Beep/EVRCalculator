import React from "react";
import assert from "node:assert/strict";
import test from "node:test";
import TestRenderer, { act } from "react-test-renderer";
import MarketExplorerRarityMarkets from "./MarketExplorerRarityMarkets";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const rarities = Array.from({ length: 39 }, (_, index) => ({
  key: `rarity-${index + 1}`,
  label: index === 0 ? "Rare Secret" : `Canonical Rarity ${index + 1}`,
}));
const prepared = [{
  market_key: "rarity:rare-secret",
  market_type: "prepared_rarity",
  label: "Rare Secret",
  metadata: { segmentId: "rarity-1" },
}];

const mount = async (props = {}) => {
  let renderer;
  await act(async () => {
    renderer = TestRenderer.create(<MarketExplorerRarityMarkets
      directory={prepared}
      rarityOptions={rarities}
      canUse
      onSelect={() => {}}
      onAddQuery={async () => "added"}
      onRemoveQuery={() => {}}
      {...props}
    />);
  });
  await act(async () => renderer.root.findByProps({ "data-rarity-market-trigger": true }).props.onClick());
  return renderer;
};

test("canonical rarity authority is not constrained to the nine prepared markets", async () => {
  const renderer = await mount();
  assert.equal(renderer.root.findAll((node) => node.props?.["data-rarity-market"]).length, 39);
});

test("rarity search filters live and prepared versus unprepared routes stay distinct", async () => {
  const selections = [];
  const queries = [];
  const renderer = await mount({
    onSelect: (key) => selections.push(key),
    onAddQuery: async (spec) => { queries.push(spec); return "added"; },
  });
  const search = renderer.root.findByProps({ "data-rarity-market-search": true });
  await act(async () => search.props.onChange({ target: { value: "secret" } }));
  let rows = renderer.root.findAll((node) => node.props?.["data-rarity-market"]);
  assert.equal(rows.length, 1);
  await act(async () => rows[0].props.onClick());
  assert.deepEqual(selections, ["rarity:rare-secret"]);
  assert.equal(queries.length, 0);

  await act(async () => search.props.onChange({ target: { value: "canonical rarity 39" } }));
  rows = renderer.root.findAll((node) => node.props?.["data-rarity-market"]);
  await act(async () => rows[0].props.onClick());
  assert.deepEqual(queries[0].segmentIds, ["rarity-39"]);
});

test("an active rarity visibly removes through the same semantic identity", async () => {
  const removed = [];
  const renderer = await mount({
    activeSeries: [{ key: "query:rare-39", spec: { asset: "cards", mode: "all", segmentIds: ["rarity-39"], eraIds: [], setIds: [], pokemonIds: [], priceSegmentIds: [], releaseAgeCohortIds: [] } }],
    onRemoveQuery: (key) => removed.push(key),
  });
  const row = renderer.root.findByProps({ "data-rarity-market": "rarity-39" });
  assert.equal(row.props["aria-selected"], true);
  assert.equal(row.props.children[1].props.children, "Remove");
  await act(async () => row.props.onClick());
  assert.deepEqual(removed, ["query:rare-39"]);
});
