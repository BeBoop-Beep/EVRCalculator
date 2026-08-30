import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const lazy = fs.readFileSync(new URL("./RankingsLazyClient.jsx", import.meta.url), "utf8");

test("Rankings owns one publication and identity scoped session cache", () => {
  assert.match(lazy, /createRankingsSessionCache\(`\$\{requestKey\}:\$\{publicationIdentity\}`\)/);
  assert.match(lazy, /sessionCache\.peek\("eras:rankings"\)/);
  assert.match(lazy, /sessionCache\.peek\("sets:rankings"\)/);
  assert.match(lazy, /sessionCache\.request\("products:full_market"/);
});

test("idle warming is sequential, conservative, and entitlement aware", () => {
  assert.match(lazy, /requestIdleCallback/);
  assert.match(lazy, /navigator\.connection\?\.saveData/);
  const order = ["lensModules.eras", "lensModules.eraEconomics", "loadEra()", "loadSets()", "warmProducts()", "warmCards()"];
  let cursor = -1;
  for (const item of order) { cursor = lazy.indexOf(item, cursor + 1); assert.ok(cursor >= 0, item); }
  assert.match(lazy, /canViewCardChaseEfficiency \? Promise\.all/);
});

test("hover, focus, and click intent escalates the selected lens", () => {
  for (const lens of ["eras", "sets", "products", "cards"]) assert.ok(lazy.includes(`onIntent: () => signalIntent("${lens}")`));
});

test("Era Rankings is public while paid lenses remain entitlement aware", () => {
  const loader = lazy.slice(lazy.indexOf("const loadEra"), lazy.indexOf("const loadSets"));
  assert.doesNotMatch(loader, /canViewRankingsIntelligence|status: "locked"/);
  assert.match(lazy, /canViewCardChaseEfficiency/);
  assert.match(lazy, /canViewRankingsIntelligence=\{canViewRankingsIntelligence\}/);
});
