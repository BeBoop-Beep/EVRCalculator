import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

const here = path.dirname(new URL(import.meta.url).pathname.slice(1));
const read = (relative) => fs.readFileSync(path.resolve(here, relative), "utf8").replace(/\r\n/g, "\n");
const shared = read("TableSearchInput.jsx");
const market = read("../explore/SetMarketExplorer.jsx");
const sets = read("../explore/ExploreTableClient.jsx");
const products = read("../explore/ProductFamilyRankingsClient.jsx");
const dimensions = ["min-h-11", "px-2.5", "py-1", "text-xs", "desk:min-h-0", "desk:py-1.5", "desk:max-w-[16rem]"];

test("TableSearchInput owns the canonical Set Market search shape", () => {
  assert.match(shared, /styles\.setMarketControl/);
  for (const dimension of dimensions) assert.ok(shared.includes(dimension), `shared search owns ${dimension}`);
  assert.match(shared, /Set Market is the visual authority/);
});

test("all table-ranking surfaces use the shared search without local dimensions", () => {
  for (const [name, source] of [["Market", market], ["Sets", sets], ["Products", products]]) {
    assert.match(source, /import TableSearchInput from "@\/components\/ui\/TableSearchInput"/);
    assert.match(source, /<TableSearchInput/);
    assert.doesNotMatch(source, /<input type="search"/);
    assert.doesNotMatch(source, /styles\.setMarketControl/);
    assert.doesNotMatch(source, /<input[^>]+(?:min-h-11|px-2\.5|desk:py-1\.5)/s, `${name} has no competing inline search dimensions`);
  }
});

test("the product toolbar reserves the canonical desktop width", () => {
  assert.ok(products.includes("md:grid-cols-[minmax(0,1fr)_16rem_minmax(18rem,1fr)]"));
  assert.ok(!products.includes("minmax(14rem,17rem)"));
});

test("the Sets toolbar reserves and centers the canonical desktop width", () => {
  assert.ok(sets.includes("md:grid-cols-[minmax(0,1fr)_16rem_minmax(0,1fr)]"));
  assert.ok(sets.includes('containerClassName="md:justify-self-center"'));
});
