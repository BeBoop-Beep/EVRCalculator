import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const cards = fs.readFileSync(new URL("./CardChaseEfficiencyRankings.jsx", import.meta.url), "utf8");
const parent = fs.readFileSync(new URL("./ProductFamilyRankingsClient.jsx", import.meta.url), "utf8");

test("RIP hierarchy ends with Cards without changing the existing lenses", () => {
  const labels = ["Overall", "Eras", "Sets", "Products", "Cards"];
  let cursor = -1;
  for (const label of labels) { const next = parent.indexOf(`label: "${label}"`, cursor + 1); assert.ok(next > cursor, label); cursor = next; }
  assert.match(parent, /view === "cards"/);
  assert.match(parent, /<CardChaseEfficiencyRankings/);
});

test("locked Cards is discoverable but cannot fetch Premium rows", () => {
  assert.match(cards, /if \(!entitled\) return <LockedCards/);
  assert.match(cards, /if \(!entitled\) \{[\s\S]*setResult\(\{ status: "idle", payload: null \}\);[\s\S]*return undefined/);
  assert.match(cards, /data-card-chase-efficiency-locked/);
});

test("filters and sorting are sent to the backend and rows are never re-ranked locally", () => {
  for (const key of ["search", "era", "set", "rarity", "min_price", "max_price", "sort", "direction", "page", "page_size"]) assert.ok(cards.includes(key), key);
  assert.match(cards, /fetch\(`\/api\/explore\/card-chase-efficiency\?\$\{params\}`/);
  assert.doesNotMatch(cards, /rows\.(sort|filter)\(/);
  assert.match(cards, /sort: "chase_efficiency", direction: "desc"/);
});

test("desktop table and mobile cards are intentional separate renderings", () => {
  assert.match(cards, /hidden overflow-x-auto desk:block/);
  assert.match(cards, /desk:hidden/);
  for (const heading of ["Rank","Card / Set","Rarity","Market Price","Pull Odds","50% Chase Cost","Cost vs Buy","Chase Efficiency"]) assert.ok(cards.includes(heading), heading);
});

test("exact card links preserve canonical and variant identity", () => {
  assert.match(cards, /buildPokemonCardDetailHref/);
  assert.match(cards, /canonicalCardId: row\?\.canonicalCardId/);
  assert.match(cards, /cardVariantId: row\?\.cardVariantId/);
});

test("pagination uses authoritative totals and never appends pages", () => {
  assert.match(cards, /setPage\(1\)/);
  assert.match(cards, /result\.payload\?\.totalPages/);
  assert.doesNotMatch(cards, /\.\.\.current.*rows/);
});
