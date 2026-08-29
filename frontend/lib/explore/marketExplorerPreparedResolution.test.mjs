import test from "node:test";
import assert from "node:assert/strict";
import { resolvePreparedSeriesForSpec } from "./marketExplorerPreparedResolution.mjs";
const series = [{ key: "raw", available: true }, { key: "sealedMarket", available: true }, { key: "sir", group: "card", parentSeriesId: "raw", isParent: false, backendKey: "sir", available: true }, { key: "bundle", group: "sealed", isParent: false, backendKey: "bundle", available: true }];

test("global parent drafts resolve to prepared parents", () => {
  assert.equal(resolvePreparedSeriesForSpec({ asset: "cards" }, series)?.key, "raw");
  assert.equal(resolvePreparedSeriesForSpec({ asset: "sealed" }, series)?.key, "sealedMarket");
});
test("exact global segments resolve by backend identity", () => {
  assert.equal(resolvePreparedSeriesForSpec({ asset: "cards", segmentIds: ["sir"] }, series)?.key, "sir");
  assert.equal(resolvePreparedSeriesForSpec({ asset: "sealed", segmentIds: ["bundle"] }, series)?.key, "bundle");
});
test("scoped, multi-segment, and ranked drafts use queries", () => {
  assert.equal(resolvePreparedSeriesForSpec({ asset: "cards", eraIds: ["sv"] }, series), null);
  assert.equal(resolvePreparedSeriesForSpec({ asset: "cards", segmentIds: ["sir", "ir"] }, series), null);
  assert.equal(resolvePreparedSeriesForSpec({ asset: "cards", segmentIds: ["sir"], mode: "chase" }, series), null);
});
