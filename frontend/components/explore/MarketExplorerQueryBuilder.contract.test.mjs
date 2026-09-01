import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
const read = (name) => readFile(new URL(name, import.meta.url), "utf8");

test("the left rail is the only market builder", async () => {
  const [client, builder] = await Promise.all([read("./MarketExplorerClient.jsx"), read("./MarketExplorerQueryBuilder.jsx")]);
  assert.ok(client.includes("<MarketExplorerQueryBuilder"));
  for (const obsolete of ['id="buildAMarket"', "scopeHandoff", "handOffToBuilder", "Use in Build a Market", "<MarketExplorerFilters"]) assert.ok(!client.includes(obsolete));
  assert.match(builder, />\s*Market Builder\s*<\/h2>/);
});

test("asset-first hierarchy owns repeated canonical scope controls", async () => {
  const source = await read("./MarketExplorerQueryBuilder.jsx");
  for (const required of ['title="Raw Cards"', "All Raw Cards", 'title="Era & Set"', 'title={asset === QUERY_ASSET_CARDS ? "Rarity" : "Product Family"}', 'title="Sealed"', "All Sealed", 'title="Graded"', 'badge="Unavailable"', 'title="Benchmarks"', "assetControls(QUERY_ASSET_CARDS)", "assetControls(QUERY_ASSET_SEALED)"]) assert.ok(source.includes(required), `missing ${required}`);
});

test("draft, commit, duplicate, and mobile controls are explicit", async () => {
  const source = await read("./MarketExplorerQueryBuilder.jsx");
  for (const marker of ["useMarketExplorerBuilderDraft", "data-current-market-preview", "data-market-builder-clear", "data-market-builder-build", "Already Active", "onAddPrepared?.(prepared.key)", "onAddQuery?.(spec)", "data-market-builder-mobile-toggle", "data-market-builder-scroll-region"]) assert.ok(source.includes(marker), `missing ${marker}`);
  assert.ok(!source.includes("marketPrice"));
});

test("active markets and existing analysis remain mounted", async () => {
  const source = await read("./MarketExplorerClient.jsx");
  for (const component of ["MarketExplorerActiveMarkets", "MarketExplorerConstituents", "MarketExplorerDetails", "MarketExplorerMethodology"]) assert.ok(source.includes(`<${component}`));
  assert.ok(source.includes("...querySeries"));
});

test("comparison analysis precedes one-market constituent inspection", async () => {
  const source = await read("./MarketExplorerClient.jsx");
  assert.ok(source.indexOf("<MarketExplorerDetails") < source.indexOf("<MarketExplorerConstituents"));
  assert.ok(source.includes("timeframe={timeframe}"));
});
