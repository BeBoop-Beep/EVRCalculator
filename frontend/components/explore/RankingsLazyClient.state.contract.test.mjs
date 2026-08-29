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
  const order = ["lensModules.eraEconomics", "loadEra()", "loadSets()", "warmProducts()", "warmCards()"];
  let cursor = -1;
  for (const item of order) { cursor = lazy.indexOf(item, cursor + 1); assert.ok(cursor >= 0, item); }
  assert.match(lazy, /canViewCardChaseEfficiency \? Promise\.all/);
});

test("hover, focus, and click intent escalates the selected lens", () => {
  for (const lens of ["eras", "sets", "products", "cards"]) assert.ok(lazy.includes(`onIntent: () => signalIntent("${lens}")`));
});

test("auth transitions are identity-scoped and distinguish locked data", () => {
  assert.match(lazy, /authStatus !== "resolved"/);
  assert.match(lazy, /status: "locked"/);
  assert.match(lazy, /Index Plus or Premium/);
});
