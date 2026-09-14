import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(here, "MarketExplorerQueryBuilder.jsx"), "utf8");

test("Builder has one compact My Markets foundation below normal research controls", () => {
  const myMarkets = source.indexOf('id="myMarkets"');
  assert.ok(myMarkets > source.indexOf('id="gradedBuilder"'));
  assert.ok(source.includes("data-market-personal-foundation"));
});

test("personal foundation states value semantics and never fabricates Wishlist analytics", () => {
  assert.match(source, /Value history is not Market Index performance/);
  assert.match(source, /Wishlist · Unavailable/);
  assert.match(source, /saved Wishlist membership is published/);
  const block = source.slice(source.indexOf('id="myMarkets"'), source.indexOf('id="myMarkets"') + 1800);
  assert.doesNotMatch(block, /mock|chartData|points=|series=/i);
});
