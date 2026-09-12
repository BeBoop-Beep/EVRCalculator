import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (name) => readFile(new URL(name, import.meta.url), "utf8");

test("directory selection is immediate, keyboard accessible, and visually distinct", async () => {
  const browse = await read("./MarketExplorerBrowse.jsx");
  assert.match(browse, /aria-pressed=\{active\}/);
  assert.match(browse, /border-\[rgb\(45,212,191\)\]/);
  assert.match(browse, /border-sky-400 bg-sky-400\/10/);
  for (const key of ["ArrowDown", "ArrowUp", "Enter", "Escape"]) assert.match(browse, new RegExp(`event\\.key === "${key}"`));
  assert.match(browse, /openHighlighted\(\)/);
});

test("Analyze owns canonical rarity markets and Screens before Build", async () => {
  const client = await read("./MarketExplorerClient.jsx");
  const rarity = await read("./MarketExplorerRarityMarkets.jsx");
  const analyze = client.indexOf('data-market-explorer-sidebar-section="analyze"');
  const rarityMount = client.indexOf("<MarketExplorerRarityMarkets", analyze);
  const screens = client.indexOf("<MarketExplorerScreens", analyze);
  const build = client.indexOf('data-market-explorer-zone="build"');
  assert.ok(analyze < rarityMount && rarityMount < screens && screens < build);
  assert.match(rarity, /Special Illustration Rare/);
  assert.match(rarity, /\.filter\(Boolean\)/);
  assert.match(rarity, /aria-pressed=\{active\}/);
});

test("Active Markets anchors actions and delegates Clear all to clearGraph", async () => {
  const client = await read("./MarketExplorerClient.jsx");
  const active = await read("./MarketExplorerActiveMarkets.jsx");
  assert.match(client, /onClearAll=\{clearGraph\}/);
  assert.match(active, /data-market-explorer-active-clear-all/);
  assert.match(active, /data-market-explorer-active-chip-scroll className="min-w-0 overflow-x-auto"/);
  assert.ok(active.indexOf("data-market-explorer-active-clear-all") < active.indexOf("data-market-explorer-active-chip-scroll"));
});

test("Builder defaults collapsed and Exact Basket advertises individual selection", async () => {
  const builder = await read("./MarketExplorerQueryBuilder.jsx");
  const exact = await read("./MarketExplorerExactBasket.jsx");
  assert.doesNotMatch(builder, /hidden min-h-0 flex-1 flex-col desk:flex/);
  assert.match(exact, /Pick individual cards or sealed products/);
});
