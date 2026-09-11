import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const picker = await readFile(new URL("./MarketExplorerExactItemPicker.jsx", import.meta.url), "utf8");
const exact = await readFile(new URL("./MarketExplorerExactBasket.jsx", import.meta.url), "utf8");
const builder = await readFile(new URL("./MarketExplorerQueryBuilder.jsx", import.meta.url), "utf8");
const client = await readFile(new URL("./MarketExplorerClient.jsx", import.meta.url), "utf8");

test("Exact Basket is one standalone top-level Premium workspace", () => {
  assert.match(client, /<MarketExplorerExactBasket/);
  assert.doesNotMatch(builder, /<MarketExplorerExactItemPicker/);
  assert.match(exact, /requires Index Premium/i);
});

test("mixed search scopes affect discovery and preserve qualified selection", () => {
  assert.match(picker, /useState\("all"\)/);
  assert.match(picker, /\["all", "cards", "sealed"\]/);
  assert.match(picker, /item\.asset.*item\.instrumentId/);
  assert.match(picker, /25 \/ 25 selected/);
});

test("Exact has no Builder narrowing or composition controls", () => {
  assert.doesNotMatch(picker, /narrowingSummary|Additional Builder filters|Clear narrowing filters/);
  assert.doesNotMatch(exact, /eraIds|setIds|segmentIds|pokemonIds|priceSegmentIds|releaseAgeCohortIds|topN/);
});

test("editing restores definition authority and translates V1 in memory", () => {
  assert.match(exact, /contractVersion === MARKET_EXPLORER_EXPLICIT_QUERY_CONTRACT_VERSION/);
  assert.match(exact, /spec\.instrumentIds/);
  assert.match(exact, /spec\.instruments/);
  assert.match(exact, /onUpdateQuery/);
  assert.match(picker, /Save as new/);
});

test("one-unit methodology and DB-owned price/share fields are explicit", () => {
  assert.match(picker, /One physical unit/);
  assert.match(picker, /item\.marketPrice/);
  assert.match(picker, /item\.valueSharePercent/);
});
