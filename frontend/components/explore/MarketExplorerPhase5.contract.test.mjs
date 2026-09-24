import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8");
const browse = read("./MarketExplorerBrowse.jsx");
const screens = read("./MarketExplorerScreens.jsx");
const context = read("./MarketExplorerContextRanking.jsx");
const client = read("./MarketExplorerClient.jsx");

test("Phase 5 prepared discovery is outside the Custom Builder", () => {
  assert.match(client, /<MarketExplorerBrowse/);
  assert.match(client, /<MarketExplorerScreens/);
  assert.doesNotMatch(`${browse}${screens}${context}`, /query\/preflight|onAddQuery|Build Market|claim.*lease/i);
});

test("Basic browse and explicit compare are separate actions", () => {
  assert.match(browse, /data-prepared-market=/);
  assert.match(browse, /data-compare-market=/);
  assert.match(client, /Compare markets with Index\+/);
  assert.match(client, /preparedLoader\.replace\(seriesId\)/);
});

test("Sets group by Era and Screens use only the prepared endpoint", () => {
  assert.match(browse, /grouped\.sets\.flatMap/);
  assert.match(browse, /groups\.map\(\(group\)/);
  assert.match(screens, /kind: "screen"/);
  assert.match(context, /kind: "ranking"/);
  assert.doesNotMatch(screens, /resolveScreenResults/);
});

test("one constituent workspace precedes lower comparison detail and Set analysis", () => {
  const styles = read("./explore.module.css");
  const detailsIndex = client.indexOf("<MarketExplorerDetails");
  const constituentsIndex = client.indexOf("<MarketExplorerConstituents");
  const contextIndex = client.indexOf("<MarketExplorerContextRanking");
  const methodologyIndex = client.indexOf("<MarketExplorerMethodology");

  assert.ok(constituentsIndex < detailsIndex);
  assert.ok(detailsIndex < contextIndex);
  assert.ok(contextIndex < methodologyIndex);
  assert.equal(client.match(/<MarketExplorerConstituents/g)?.length, 1);
  assert.doesNotMatch(client, /explorerInspectionGrid/);
  assert.doesNotMatch(styles, /explorerInspectionGrid/);
  assert.match(client, /activeDetailMarket\?\.marketType === "set"/);
  assert.match(context, /Selected Set Analysis/);
});
