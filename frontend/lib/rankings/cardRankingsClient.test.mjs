import assert from "node:assert/strict";
import test from "node:test";
import { buildCardRowsParams } from "./cardRankingsClient.mjs";

test("Collector query is page-first and omits empty filters", () => {
  const params = buildCardRowsParams({ lens: "pokemon", page: 3, filters: { search: "Sylveon", era: "era-1", set: "set-1", rarity: "", sort: "rank", direction: "asc" } });
  assert.equal(params.get("lens"), "pokemon");
  assert.equal(params.get("page"), "3");
  assert.equal(params.get("page_size"), "50");
  assert.equal(params.get("set"), "set-1");
  assert.equal(params.has("rarity"), false);
});

test("Chase query does not inherit a Collector component lens", () => {
  const params = buildCardRowsParams({ page: 1, filters: { search: "", era: "", set: "", rarity: "SIR", min_price: "", max_price: "", sort: "rank", direction: "asc" } });
  assert.equal(params.has("lens"), false);
  assert.equal(params.get("rarity"), "SIR");
});
