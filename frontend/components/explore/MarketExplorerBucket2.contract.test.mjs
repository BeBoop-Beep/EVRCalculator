import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (name) => readFile(new URL(name, import.meta.url), "utf8");

test("sidebar keeps Browse and Analyze while the visible Builder is exact-only", async () => {
  const client = await read("./MarketExplorerClient.jsx");
  const picker = await read("./MarketExplorerExactItemPicker.jsx");
  const explore = client.indexOf('data-market-explorer-zone="explore"');
  const browse = client.indexOf("<MarketExplorerBrowse", explore);
  const analyze = client.indexOf('data-market-explorer-sidebar-section="asset-markets"', browse);
  const rarity = client.indexOf("<MarketExplorerRarityMarkets", analyze);
  const screens = client.indexOf("<MarketExplorerScreens", rarity);
  const sidebarEnd = client.indexOf("</aside>", screens);
  const build = client.indexOf('data-market-explorer-zone="build"', sidebarEnd);
  const exact = client.indexOf("<MarketExplorerExactBasket", build);
  assert.ok(explore < browse && browse < analyze && analyze < rarity && rarity < screens && screens < sidebarEnd && sidebarEnd < build && build < exact);
  assert.doesNotMatch(client, /data-market-explorer-sidebar-section="filter"|Filter · Premium|setFiltersOpen/);
  assert.equal(client.match(/<MarketExplorerQueryBuilder/g)?.length || 0, 0);
  assert.doesNotMatch(client, /Custom Filters|builderMode/);
  assert.match(picker, /MAX_EXPLICIT_INSTRUMENTS/);
  assert.match(client, /data-market-explorer-build-path="exact"/);
});

test("Rarity Markets uses every prepared rarity dynamically with search and compare/remove", async () => {
  const rarity = await read("./MarketExplorerRarityMarkets.jsx");
  const selector = await read("./MarketExplorerAssetMarketSelector.jsx");
  assert.match(rarity, /market_type === "prepared_rarity"/);
  assert.match(selector, /data-rarity-market-search/);
  assert.match(selector, /role="listbox"/);
  assert.match(selector, /role="option"/);
  assert.match(rarity, /onSelect\?\.\(state\.prepared\.market_key\)/);
  assert.match(selector, /option\.active \? "Remove"/);
  // No parallel fetch here: the custom-query fallback goes through the one bounded hook.
  assert.doesNotMatch(rarity, /RARITY_LABELS|fetch\s*\(|preflight/i);
});

test("Screens are public prepared discovery with local result state", async () => {
  const client = await read("./MarketExplorerClient.jsx");
  const screens = await read("./MarketExplorerScreens.jsx");
  assert.match(screens, /MARKET_EXPLORER_SCREENS[\s\S]*\.map/);
  assert.doesNotMatch(screens, /Locked|canUse|onUpgrade/);
  assert.match(screens, /aria-pressed=\{active\}/);
  assert.match(screens, /new Map\(\)/);
  assert.match(screens, /cache\.current\.has\(screen\.id\)/);
  assert.match(screens, /kind: "screen"/);
  assert.match(screens, /data-market-screen-results-for=\{selected\}/);
  assert.match(screens, /data-market-screen-retry/);
  assert.match(screens, /onSelect\(row\.market_key\)/);
  assert.match(screens, /active \? "Remove"/);
  assert.match(client, /onSelect=\{selectPrepared\}/);
  assert.doesNotMatch(screens, /onAddQuery|preflight|Build Market/);
});

test("Build modal exposes Cards & Products only while retaining the filter component off-path", async () => {
  const client = await read("./MarketExplorerClient.jsx");
  const picker = await read("./MarketExplorerExactItemPicker.jsx");
  const query = await read("./MarketExplorerQueryBuilder.jsx");
  const build = client.slice(client.indexOf('data-market-explorer-zone="build"'), client.indexOf('data-market-explorer-zone="compare"'));
  assert.match(build, /<MarketExplorerExactBasket/);
  assert.doesNotMatch(build, /<MarketExplorerQueryBuilder/);
  assert.match(picker, /All/);
  assert.match(picker, /Cards/);
  assert.match(picker, /Products/);
  assert.doesNotMatch(build, /Custom Filters/);
  assert.match(client, /series\.spec\?\.membershipMode !== "explicit"\) return/);
  assert.match(client, /setBuilderOpen\(true\)/);
  assert.match(query, /presentation === "sidebar"/);
});


test("Index+ prepared selection accumulates and compare controls toggle Remove without clearing other lanes", async () => {
  const client = await read("./MarketExplorerClient.jsx");
  const browse = await read("./MarketExplorerBrowse.jsx");
  // Lifecycle model: a compare click ADDS through the prepared loader (active only once loaded)
  // and a second click REMOVES; neither clears another lane.
  assert.match(client, /preparedLoader\.add\(seriesId\)/);
  assert.match(client, /current\.loaded\[seriesId\][\s\S]*preparedLoader\.remove\(seriesId\)/);
  const paidBlock = client.slice(client.indexOf("const comparePrepared = useCallback"), client.indexOf("const selectPrepared = useCallback"));
  assert.doesNotMatch(paidBlock, /clearAllSelection\(|clearAllQueries\(/);
  assert.match(browse, /active \? "Remove"/);
});
