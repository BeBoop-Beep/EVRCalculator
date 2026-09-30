import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (name) => readFile(new URL(name, import.meta.url), "utf8");

test("one client-owned disclosure key controls Browse, Rarity, and Sealed Types", async () => {
  const client = await read("./MarketExplorerClient.jsx");
  const browse = await read("./MarketExplorerBrowse.jsx");
  assert.match(client, /sidebarDisclosure/);
  for (const key of ["search", "sets", "eras", "quick", "rarities", "sealed-types"]) assert.match(client, new RegExp(key));
  assert.match(client, /disclosureOpen=\{sidebarDisclosure === "rarities"\}/);
  assert.match(client, /disclosureOpen=\{sidebarDisclosure === "sealed-types"\}/);
  assert.match(browse, /disclosureOpen/);
});

test("Rarity and Sealed Types compose the same presentation primitive", async () => {
  const rarity = await read("./MarketExplorerRarityMarkets.jsx");
  const sealed = await read("./MarketExplorerSealedTypes.jsx");
  const shared = await read("./MarketExplorerAssetMarketSelector.jsx");
  assert.match(rarity, /MarketExplorerAssetMarketSelector/);
  assert.match(sealed, /MarketExplorerAssetMarketSelector/);
  assert.match(shared, /ASSET_MARKET_OPTION_CLASS/);
  assert.match(shared, /data-market-asset-selector-scroll-region/);
  assert.match(shared, /Escape/);
  assert.match(shared, /composedPath/);
});

test("public discovery has truthful Basic wording and canonical rarity has no upgrade path", async () => {
  const rarity = await read("./MarketExplorerRarityMarkets.jsx");
  const screens = await read("./MarketExplorerScreens.jsx");
  assert.doesNotMatch(rarity, /Build · Upgrade|onUpgrade/);
  assert.match(rarity, /onAddCanonicalRarity/);
  assert.doesNotMatch(screens, /Locked|canUse|onUpgrade/);
  assert.match(screens, /canCompare \? "\+ Compare" : "View"/);
  assert.doesNotMatch(screens, /asset:/);
});

test("selection status is adjacent to Active Markets and absent from chart notices", async () => {
  const client = await read("./MarketExplorerClient.jsx");
  const active = client.indexOf("<MarketExplorerActiveMarkets");
  const status = client.indexOf("<PreparedMarketStatus", active);
  const chart = client.indexOf("<MarketExplorerChart", status);
  assert.ok(active < status && status < chart);
  assert.doesNotMatch(client, /data-market-explorer-workspace-notices/);
});

test("desktop Methodology and Constituents occupy their required columns", async () => {
  const client = await read("./MarketExplorerClient.jsx");
  const chart = await read("./MarketExplorerChart.jsx");
  const cardEnd = client.indexOf("</section>", client.indexOf('data-market-explorer-zone="explore"'));
  const methodology = client.indexOf("data-market-explorer-methodology-trigger", cardEnd);
  const asideEnd = client.indexOf("</aside>", methodology);
  assert.ok(cardEnd < methodology && methodology < asideEnd);
  assert.doesNotMatch(chart, /data-market-explorer-methodology-trigger/);
  assert.match(chart, /data-market-explorer-chart-bottom-actions[\s\S]*justify-center/);
  assert.match(chart, /data-market-explorer-view-details/);
});

test("workspace uses measured header height and route avoids desktop double bottom padding", async () => {
  const client = await read("./MarketExplorerClient.jsx");
  const page = await read("../../app/Market/Explorer/page.js");
  assert.match(client, /100dvh-var\(--app-header-offset,64px\)-2rem/);
  assert.doesNotMatch(client, /15\.5rem/);
  assert.match(page, /pb-20[\s\S]*desk:pb-4/);
});
