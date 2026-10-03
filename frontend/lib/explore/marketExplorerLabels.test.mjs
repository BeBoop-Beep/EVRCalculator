import test from "node:test";
import assert from "node:assert/strict";
import { formatExplorerMarketLabel } from "./marketExplorerLabels.mjs";

test("Set markets use generic singular asset-market identity", () => {
  assert.equal(formatExplorerMarketLabel({ label: "Prismatic Evolutions", asset: "cards", market_type: "set" }), "Prismatic Evolutions Card Market");
  assert.equal(formatExplorerMarketLabel({ label: "Prismatic Evolutions — Cards", asset: "cards", market_type: "set" }), "Prismatic Evolutions Card Market");
  assert.equal(formatExplorerMarketLabel({ label: "Prismatic Evolutions - Sealed", asset: "sealed", market_type: "set" }), "Prismatic Evolutions Sealed Market");
  assert.equal(formatExplorerMarketLabel({ label: "Journey Together", asset: "sealed", market_type: "set" }), "Journey Together Sealed Market");
});

test("physical instruments and non-Set markets retain existing naming", () => {
  assert.equal(formatExplorerMarketLabel({ label: "Charizard ex", asset: "cards", market_type: "physical" }), "Charizard ex — Cards");
  assert.equal(formatExplorerMarketLabel({ label: "Raw Card Market", asset: "cards", market_type: "parent" }), "Raw Card Market — Cards");
});
