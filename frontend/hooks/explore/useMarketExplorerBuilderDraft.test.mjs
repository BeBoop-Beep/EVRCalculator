import test from "node:test";
import assert from "node:assert/strict";
import { INITIAL_MARKET_EXPLORER_BUILDER_DRAFT, marketExplorerBuilderDraftReducer } from "../../lib/explore/marketExplorerBuilderDraft.mjs";

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
