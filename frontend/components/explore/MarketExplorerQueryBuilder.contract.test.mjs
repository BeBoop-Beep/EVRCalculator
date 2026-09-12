import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
const read = (name) => readFile(new URL(name, import.meta.url), "utf8");

test("filtered and explicit builders have one accepted owner each", async () => {
  const [client, builder] = await Promise.all([read("./MarketExplorerClient.jsx"), read("./MarketExplorerQueryBuilder.jsx")]);
  assert.equal(client.match(/<MarketExplorerQueryBuilder/g)?.length, 1);
  assert.equal(client.match(/<MarketExplorerExactBasket/g)?.length, 1);
  assert.match(client, /data-market-explorer-zone="build"/);
  for (const obsolete of ['id="buildAMarket"', "scopeHandoff", "handOffToBuilder", "Use in Build a Market", "<MarketExplorerFilters"]) assert.ok(!client.includes(obsolete));
  assert.match(builder, /Custom Filtered Market/);
});

test("the Custom Filters builder owns canonical scope and filter controls", async () => {
  const source = await read("./MarketExplorerQueryBuilder.jsx");
  for (const required of ['title="Raw Cards"', 'title="Era & Set"', 'title={asset === QUERY_ASSET_CARDS ? "Rarity" : "Product Family"}', 'title="Sealed"', 'title="Graded"', 'badge="Unavailable"', "assetControls(QUERY_ASSET_CARDS)", "assetControls(QUERY_ASSET_SEALED)"]) assert.ok(source.includes(required), `missing ${required}`);
  for (const removed of ["Edit this asset", "All Raw Cards", "All Sealed", "Use in Market Builder"]) assert.ok(!source.includes(removed), `obsolete handoff remains: ${removed}`);
});

test("draft, commit, duplicate, and mobile controls are explicit", async () => {
  const source = await read("./MarketExplorerQueryBuilder.jsx");
  for (const marker of ["useMarketExplorerBuilderDraft", "data-current-market-preview", "data-market-builder-clear", "data-market-builder-build", "Already Active", "onAddPrepared?.(prepared.key)", "onAddQuery?.(spec,", "data-market-builder-mobile-toggle", "data-market-builder-scroll-region"]) assert.ok(source.includes(marker), `missing ${marker}`);
  assert.ok(!source.includes("marketPrice"));
});

test("active markets and existing analysis remain mounted", async () => {
  const source = await read("./MarketExplorerClient.jsx");
  for (const component of ["MarketExplorerActiveMarkets", "MarketExplorerConstituents", "MarketExplorerDetails", "MarketExplorerMethodology"]) assert.ok(source.includes(`<${component}`));
  assert.ok(source.includes("...querySeries"));
});

test("comparison analysis and one-market constituent inspection remain distinct", async () => {
  const source = await read("./MarketExplorerClient.jsx");
  assert.ok(source.includes("<MarketExplorerDetails"));
  assert.ok(source.includes("<MarketExplorerConstituents"));
  assert.ok(source.includes("timeframe={timeframe}"));
});
