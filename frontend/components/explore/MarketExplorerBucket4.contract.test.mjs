import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const client = read("./MarketExplorerClient.jsx");
const chart = read("./MarketExplorerChart.jsx");
const activeMarkets = read("./MarketExplorerActiveMarkets.jsx");
const constituents = read("./MarketExplorerConstituents.jsx");
const rarity = read("./MarketExplorerRarityMarkets.jsx");
const sealed = read("./MarketExplorerSealedTypes.jsx");

test("below desktop uses one floating controls trigger outside the graph and actions", () => {
  assert.doesNotMatch(client, /Markets \/ Tools/);
  assert.match(client, /data-market-explorer-mobile-tools/);
  assert.match(client, /aria-label=\{mobileToolsOpen \? "Close Market controls" : "Open Market controls"\}/);
  assert.match(client, /top-\[calc\(var\(--app-header-offset,64px\)\+0\.75rem\)\]/);
  assert.match(client, /data-market-explorer-active-strip[\s\S]*?pr-16 desk:pr-0/);
  assert.match(client, /desk:hidden/);
});

test("responsive controls are a modal overlay that reuses the desktop sidebar tree", () => {
  assert.equal((client.match(/data-market-explorer-sidebar(?:\s|>)/g) || []).length, 1);
  assert.equal((client.match(/const \[sidebarDisclosure/g) || []).length, 1);
  assert.equal((client.match(/<MarketExplorerRarityMarkets/g) || []).length, 1);
  assert.equal((client.match(/<MarketExplorerSealedTypes/g) || []).length, 1);
  assert.match(rarity, /MarketExplorerAssetMarketSelector/);
  assert.match(sealed, /MarketExplorerAssetMarketSelector/);
  assert.match(client, /role="dialog"/);
  assert.match(client, /aria-modal=\{mobileToolsOpen/);
  assert.match(client, /data-market-explorer-controls-backdrop/);
  assert.match(client, /overflow-y-auto overscroll-contain/);
});

test("drawer lifecycle locks body, traps focus, closes on Escape, and restores trigger focus", () => {
  assert.match(client, /document\.body\.style\.overflow = "hidden"/);
  assert.match(client, /document\.body\.style\.overflow = previousOverflow/);
  assert.match(client, /event\.key === "Escape"/);
  assert.match(client, /event\.key !== "Tab"/);
  assert.match(client, /data-market-explorer-close-controls/);
  assert.match(client, /trigger\?\.focus/);
});

test("mobile analysis actions share one violet row while desktop positions remain intact", () => {
  assert.match(client, /data-market-explorer-mobile-analysis-actions[^>]*className="order-3 grid flex-none grid-cols-2/);
  assert.match(client, /data-market-explorer-mobile-methodology/);
  assert.match(client, /data-market-explorer-mobile-constituents/);
  assert.match(client, /text-violet-100/);
  assert.match(client, /data-market-explorer-methodology-trigger[\s\S]*?desk:block/);
  assert.match(client, /desk:col-start-1/);
  assert.match(client, /desk:col-start-2/);
});

test("responsive analysis is viewport-bounded and yields plot height before actions", () => {
  const workspace = client.match(/data-market-explorer-workspace[\s\S]*?className="([^"]+)"/)?.[1] || "";
  const analysis = client.match(/data-market-explorer-analysis[\s\S]*?className="([^"]+)"/)?.[1] || "";
  const actions = client.match(/data-market-explorer-mobile-analysis-actions[^>]*className="([^"]+)"/)?.[1] || "";
  assert.match(workspace, /h-\[calc\(100dvh-var\(--app-header-offset,64px\)-5\.25rem-env\(safe-area-inset-bottom\)-1\.5rem\)\]/);
  assert.match(workspace, /min-h-0/);
  assert.match(workspace, /overflow-hidden/);
  assert.match(analysis, /h-full/);
  assert.match(analysis, /min-h-0/);
  assert.doesNotMatch(analysis, /min-h-\[32rem\]|tab:min-h-/);
  assert.match(actions, /flex-none/);
});

test("responsive chart is a shrinking flex child, not a fixed-height plot", () => {
  assert.doesNotMatch(chart, /h-\[20rem\]|tab:h-\[26rem\]/);
  assert.match(chart, /className="flex h-full min-h-0 flex-col"/);
  assert.match(chart, /plotClassName="min-h-\[4rem\] flex-1 desk:min-h-\[12rem\] \[@media\(max-height:500px\)\]:min-h-0"/);
  assert.match(chart, /\[@media\(max-height:500px\)\]:hidden/);
  assert.match(activeMarkets, /\[@media\(max-height:500px\)\]:gap-1/);
  assert.match(activeMarkets, /text-\[var\(--text-secondary\)\] \[@media\(max-height:500px\)\]:hidden/);
  assert.match(chart, /data-market-explorer-chart-bottom-actions[^>]*hidden[^"]*desk:flex/);
});

test("graph stays mounted and is inert only while responsive controls overlay it", () => {
  assert.equal((client.match(/<MarketExplorerChart/g) || []).length, 1);
  assert.match(client, /inert=\{mobileToolsOpen \? true : undefined\}/);
  assert.doesNotMatch(client, /mobileToolsOpen\s*\?\s*<MarketExplorerChart/);
});

test("all seven movement windows remain horizontally reachable without changing semantics", () => {
  assert.match(constituents, /CONSTITUENT_MOVEMENT_WINDOWS\.map/);
  assert.match(constituents, /overflow-x-auto/);
  assert.match(constituents, /shrink-0 rounded/);
  assert.match(constituents, /ChangeCell/);
});
