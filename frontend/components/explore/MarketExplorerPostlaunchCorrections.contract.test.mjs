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

