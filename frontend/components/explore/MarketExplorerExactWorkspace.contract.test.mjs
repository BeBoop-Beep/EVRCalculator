import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const picker = await readFile(new URL("./MarketExplorerExactItemPicker.jsx", import.meta.url), "utf8");
const exact = await readFile(new URL("./MarketExplorerExactBasket.jsx", import.meta.url), "utf8");
const builder = await readFile(new URL("./MarketExplorerQueryBuilder.jsx", import.meta.url), "utf8");
const client = await readFile(new URL("./MarketExplorerClient.jsx", import.meta.url), "utf8");

test("Build Your Market is one direct Premium instrument workspace", () => {
  assert.equal((client.match(/role="dialog"/g) || []).length, 1);
  assert.match(client, /<MarketExplorerExactBasket/);
  assert.match(exact, /<MarketExplorerExactItemPicker/);
  assert.doesNotMatch(builder, /<MarketExplorerExactItemPicker/);
  assert.doesNotMatch(`${picker}${exact}`, />Exact Basket<|Create Exact Basket|Build Basket|Update Basket/);
  assert.doesNotMatch(picker, /className="fixed inset-0|role="dialog"/);
  assert.match(exact, /requires Index Premium/i);
});

test("Cards and Products scopes preserve qualified canonical search", () => {
  assert.match(picker, /useState\("all"\)/);
  assert.match(picker, /value: "all", label: "All"/);
  assert.match(picker, /value: "cards", label: "Cards"/);
  assert.match(picker, /value: "sealed", label: "Products"/);
  assert.match(picker, /instruments\/search\?q=/);
  assert.match(picker, /asset=\$\{scope\}/);
  assert.match(picker, /item\.asset.*item\.instrumentId/);
  assert.match(picker, /25 \/ 25 selected — remove an item to add another/);
});

test("the modal has stable header, scroll body, and footer without redundant Close", () => {
  assert.match(picker, /<header className=/);
  assert.match(picker, /overflow-y-auto/);
  assert.match(picker, /<footer className="flex-none/);
  assert.match(picker, /aria-label="Close Build Your Market"/);
  assert.doesNotMatch(picker, />Close<\/button>/);
  assert.match(client, /data-market-exact-search/);
  assert.match(client, /event\.key === "Escape"/);
  assert.match(client, /data-market-explorer-build-trigger/);
});

test("editing restores V2 and V1 definitions without changing methodology", () => {
  assert.match(exact, /contractVersion === MARKET_EXPLORER_EXPLICIT_QUERY_CONTRACT_VERSION/);
  assert.match(exact, /spec\.instrumentIds/);
  assert.match(exact, /spec\.instruments/);
  assert.match(exact, /onUpdateQuery\?\.\(editingSeries\.instanceId/);
  assert.match(picker, /Save as New/);
  assert.match(exact, /Update Market/);
  assert.doesNotMatch(exact, /eraIds|setIds|segmentIds|pokemonIds|priceSegmentIds|releaseAgeCohortIds|topN/);
});

test("qualified identity, bounds, and optional DB-owned prices remain explicit", () => {
  assert.match(exact, /QUERY_MEMBERSHIP_EXPLICIT/);
  assert.match(picker, /MAX_EXPLICIT_INSTRUMENTS/);
  assert.match(picker, /item\.marketPrice != null/);
  assert.match(picker, /item\.valueSharePercent != null/);
  assert.doesNotMatch(picker, /quantity|customWeight/i);
});
