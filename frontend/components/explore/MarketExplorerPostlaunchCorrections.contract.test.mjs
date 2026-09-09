import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8").replace(/\r\n/g, "\n");

test("exact items use a dedicated accessible responsive workspace", () => {
  const picker = read("./MarketExplorerExactItemPicker.jsx");
  const builder = read("./MarketExplorerQueryBuilder.jsx");
  for (const contract of ['role="dialog"', 'aria-modal="true"', "data-market-explorer-exact-workspace", "desk:max-w-5xl", "Selected basket", "onSaveAsNew", "Clear narrowing filters"]) assert.ok(picker.includes(contract), contract);
  assert.ok(builder.includes("data-market-exact-open"));
  assert.ok(!builder.includes("<ExplorerDisclosure id={`${asset}ExactItems`"));
});

test("Screens are immediate prepared discovery and presets are a separate draft action", () => {
  const builder = read("./MarketExplorerQueryBuilder.jsx");
  assert.ok(builder.includes("Pre-built market scans."));
  assert.ok(builder.includes("No prepared markets currently qualify for this Screen."));
  assert.ok(builder.includes("MARKET_EXPLORER_QUICK_PRESETS.map"));
  assert.ok(builder.includes("One-click Builder setups."));
});

test("Explorer reads live auth and leaves one options owner", () => {
  const client = read("./MarketExplorerClient.jsx");
  const builder = read("./MarketExplorerQueryBuilder.jsx");
  const hook = read("../../hooks/explore/useMarketExplorerFilterOptions.js");
  assert.ok(client.includes("const auth = useAuth()"));
  assert.ok(client.includes("authRevision: auth?.authRevision || 0"));
  assert.ok(builder.includes("enabled: options === undefined"));
  assert.ok(hook.includes("[authRevision, enabled, isAuthenticated]"));
});

test("shared relative chart preserves raw values, labels performance, and powers Market plus Explorer", () => {
  const chart = read("./MarketPerformanceChart.jsx");
  const explorer = read("./MarketExplorerChart.jsx");
  const market = read("./PokemonMarketPerformance.jsx");
  assert.ok(chart.includes("projectMarketChartValues(entry.values || [], viewMode)"));
  assert.ok(chart.includes("rawValues: entry.values || []"));
  assert.ok(chart.includes("Market Index {reading.rawValue"));
  assert.ok(chart.includes("{timeframe} performance"));
  assert.ok(chart.includes("data-market-performance-reference={referenceValue}"));
  assert.ok(explorer.includes("<MarketPerformanceChart"));
  assert.ok(market.includes("<MarketPerformanceChart"));
});

test("build failures remain beside both CTAs with structured accessible state", () => {
  const picker = read("./MarketExplorerExactItemPicker.jsx");
  const builder = read("./MarketExplorerQueryBuilder.jsx");
  for (const state of ["idle", "building", "success", "error", "locked"]) assert.ok(builder.includes(`\"${state}\"`), state);
  assert.ok(builder.includes('role={buildStatus === "error" ? "alert" : "status"}'));
  assert.ok(picker.includes('role={buildStatus === "error" ? "alert" : "status"}'));
  assert.ok(builder.includes("error?.message ||"), "useful backend messages must survive");
});

test("accepted chart-first hierarchy remains intact", () => {
  const client = read("./MarketExplorerClient.jsx");
  assert.equal((client.match(/<MarketExplorerActiveMarkets/g) || []).length, 1);
  assert.ok(client.indexOf("<MarketExplorerConstituents") < client.indexOf("<MarketExplorerDetails"));
  assert.ok(client.indexOf("<MarketExplorerDetails") < client.indexOf("<MarketExplorerMethodology"));
  assert.ok(client.includes("data-market-explorer-active-strip"));
  assert.ok(client.includes("data-market-explorer-chart-pane") || read("./MarketExplorerChart.jsx").includes("data-market-explorer-chart-pane"));
});

