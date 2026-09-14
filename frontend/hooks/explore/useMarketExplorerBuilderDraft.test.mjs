import test from "node:test";
import assert from "node:assert/strict";
import { INITIAL_MARKET_EXPLORER_BUILDER_DRAFT, compatibleSetIds, marketExplorerBuilderDraftReducer } from "../../lib/explore/marketExplorerBuilderDraft.mjs";

test("set compatibility unions within axes and intersects across axes", () => {
  const allowed = compatibleSetIds([
    { ids: ["rarity-a", "rarity-b"], map: { "rarity-a": ["set-1"], "rarity-b": ["set-2", "set-3"] } },
    { ids: ["pokemon-x", "pokemon-y"], map: { "pokemon-x": ["set-2"], "pokemon-y": ["set-4"] } },
  ]);
  assert.deepEqual([...allowed].sort(), ["set-2"]);
});

test("switching either asset clears its segment and keeps reconciled scope", () => {
  const cards = { ...INITIAL_MARKET_EXPLORER_BUILDER_DRAFT, eraIds: ["sv"], setIds: ["shared", "cards-only"], segmentIds: ["sir"] };
  const sealed = marketExplorerBuilderDraftReducer(cards, { type: "asset", asset: "sealed", setIds: ["shared"] });
  assert.deepEqual([sealed.eraIds, sealed.setIds, sealed.segmentIds], [["sv"], ["shared"], []]);
  const back = marketExplorerBuilderDraftReducer({ ...sealed, segmentIds: ["bundle"] }, { type: "asset", asset: "cards", setIds: ["shared"] });
  assert.deepEqual([back.eraIds, back.setIds, back.segmentIds], [["sv"], ["shared"], []]);
});
test("clear resets every draft field", () => {
  const changed = { asset: "sealed", eraIds: ["sv"], setIds: ["shared"], segmentIds: ["bundle"], mode: "chase", topN: 10 };
  assert.deepEqual(marketExplorerBuilderDraftReducer(changed, { type: "clear" }), INITIAL_MARKET_EXPLORER_BUILDER_DRAFT);
});

test("exact membership keeps a removable edit definition separate from filter defaults", () => {
  const item = { instrumentId: "variant-b", name: "Charizard" };
  let state = marketExplorerBuilderDraftReducer(INITIAL_MARKET_EXPLORER_BUILDER_DRAFT, { type: "field", field: "membershipMode", value: "explicit" });
  state = marketExplorerBuilderDraftReducer(state, { type: "field", field: "exactItems", value: [item] });
  state = marketExplorerBuilderDraftReducer(state, { type: "field", field: "instrumentIds", value: [item.instrumentId] });
  assert.equal(state.membershipMode, "explicit");
  assert.deepEqual(state.instrumentIds, ["variant-b"]);
  assert.deepEqual(state.exactItems, [item]);
  const filters = marketExplorerBuilderDraftReducer(state, { type: "field", field: "membershipMode", value: "filters" });
  assert.deepEqual(filters.exactItems, [item]);
});

test("changing a peer filter exits Exact mode without leaking its saved basket", () => {
  const exact = {
    ...INITIAL_MARKET_EXPLORER_BUILDER_DRAFT,
    membershipMode: "explicit",
    instrumentIds: ["variant-a"],
    exactItems: [{ instrumentId: "variant-a" }],
  };
  const filtered = marketExplorerBuilderDraftReducer(exact, {
    type: "field", field: "segmentIds", value: ["specialIllustrationRare"],
  });
  assert.equal(filtered.membershipMode, "filters");
  assert.deepEqual(filtered.segmentIds, ["specialIllustrationRare"]);
  assert.deepEqual(filtered.instrumentIds, ["variant-a"]);
});

test("entering Exact mode removes independent filter and ranking axes", () => {
  const filtered = {
    ...INITIAL_MARKET_EXPLORER_BUILDER_DRAFT,
    eraIds: ["sv"], segmentIds: ["sir"], priceSegmentIds: ["intermediate"],
    releaseAgeCohortIds: ["new"], mode: "chase", topN: 10,
  };
  const exact = marketExplorerBuilderDraftReducer(filtered, {
    type: "field", field: "membershipMode", value: "explicit",
  });
  assert.deepEqual(exact.eraIds, []);
  assert.deepEqual(exact.segmentIds, []);
  assert.deepEqual(exact.priceSegmentIds, []);
  assert.deepEqual(exact.releaseAgeCohortIds, []);
  assert.equal(exact.mode, "all");
  assert.equal(exact.topN, null);
});
