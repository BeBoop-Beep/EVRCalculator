import test from "node:test";
import assert from "node:assert/strict";
import { formatExplorerMarketLabel } from "./marketExplorerLabels.mjs";

test("Explorer market labels are asset-aware without duplicate qualification", () => {
  assert.equal(formatExplorerMarketLabel({ label: "New Releases", asset: "cards" }), "New Releases — Cards");
  assert.equal(formatExplorerMarketLabel({ label: "New Releases", asset: "sealed" }), "New Releases — Sealed");
  assert.equal(formatExplorerMarketLabel({ label: "Emerald — Sealed", asset: "sealed" }), "Emerald — Sealed");
  assert.equal(formatExplorerMarketLabel({ label: "New Release Cards", asset: "cards" }), "New Release Cards");
});
