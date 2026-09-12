import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (name) => readFile(new URL(name, import.meta.url), "utf8");

test("Bucket 2 sidebar orders Browse, Analyze, then Premium Custom Filters", async () => {
  const client = await read("./MarketExplorerClient.jsx");
  const explore = client.indexOf('data-market-explorer-zone="explore"');
  const browse = client.indexOf("<MarketExplorerBrowse", explore);
  const analyze = client.indexOf('data-market-explorer-sidebar-section="analyze"', browse);
  const rarity = client.indexOf("<MarketExplorerRarityMarkets", analyze);
  const screens = client.indexOf("<MarketExplorerScreens", rarity);
  const filter = client.indexOf('data-market-explorer-sidebar-section="filter"', screens);
  const query = client.indexOf("<MarketExplorerQueryBuilder", filter);
  assert.ok(explore < browse && browse < analyze && analyze < rarity && rarity < screens && screens < filter && filter < query);
  assert.equal(client.match(/<MarketExplorerQueryBuilder/g)?.length, 1);
  assert.match(client, /presentation="sidebar"/);
  assert.match(client, /hidden=\{!filtersOpen\}/);
  assert.match(client, /disabled=\{!canBuildCustomMarkets\}/);
  assert.match(client, /enabled: canBuildCustomMarkets/);
});

test("Rarity Markets is a compact canonical prepared selector", async () => {
  const rarity = await read("./MarketExplorerRarityMarkets.jsx");
  assert.match(rarity, /data-rarity-market-trigger/);
  assert.match(rarity, /role="listbox"/);
  assert.match(rarity, /role="option"/);
  assert.match(rarity, /aria-selected=\{active\}/);
  assert.match(rarity, /onSelect\(market\.market_key\)/);
  assert.doesNotMatch(rarity, /fetch\s*\(|preflight|build/i);
  assert.equal((rarity.match(/^  "/gm) || []).length, 9);
});

test("Screens are independently gated prepared discovery with local result state", async () => {
  const client = await read("./MarketExplorerClient.jsx");
  const screens = await read("./MarketExplorerScreens.jsx");
  assert.match(screens, /MARKET_EXPLORER_SCREENS\.map/);
  assert.match(screens, /aria-disabled=\{!canUse\}/);
  assert.match(screens, /aria-pressed=\{active\}/);
  assert.match(screens, /new Map\(\)/);
  assert.match(screens, /cache\.current\.has\(screen\.id\)/);
  assert.match(screens, /kind: "screen"/);
  assert.match(screens, /data-market-screen-results-for=\{selected\}/);
  assert.match(screens, /data-market-screen-retry/);
  assert.match(screens, /onSelect\(row\.market_key\)/);
  assert.match(client, /onSelect=\{selectPrepared\}/);
  assert.doesNotMatch(screens, /onAddQuery|preflight|Build Market/);
});

test("Build modal is Exact Basket only while filtered editing opens the sidebar", async () => {
  const client = await read("./MarketExplorerClient.jsx");
  const query = await read("./MarketExplorerQueryBuilder.jsx");
  const build = client.slice(client.indexOf('data-market-explorer-zone="build"'), client.indexOf("</aside>"));
  assert.match(build, /<MarketExplorerExactBasket/);
  assert.doesNotMatch(build, /<MarketExplorerQueryBuilder|Custom Filtered|role="tablist"/);
  assert.match(client, /membershipMode === "explicit"\) setBuilderOpen\(true\)/);
  assert.match(client, /setFiltersOpen\(true\)/);
  assert.match(query, /presentation === "sidebar"/);
  assert.match(query, /data-market-builder-presentation="sidebar"/);
});
