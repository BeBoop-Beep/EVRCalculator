import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { readSetRipLandscape } from "./setRipLandscapeSelector.mjs";
import { SET_PACK_COLUMNS } from "./setPackMetricsSelector.mjs";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const distribution = read("./OpeningEconomicsDistribution.jsx");
const setPack = read("./SetPackMetrics.jsx");
const eraPack = read("./OpeningEconomicsEras.jsx");
const financial = read("./SetMetricRankingsTable.jsx");
const products = read("./RankingsProductLensClient.jsx");
const lazy = read("./RankingsLazyClient.jsx");

test("Set RIP landscape uses only published public rank, score, tier, and identity", () => {
  const rows = readSetRipLandscape([
    { name: "Second", logo_image_url: "/second.png", setRipV1: { publicScore: 81, score: 999, rank: 2, tier: "A" }, financialRipV4: { leaderNormalizedScore: 100 } },
    { name: "First", setRipV1: { publicScore: 92, rank: 1, tier: "S" } },
    { name: "Unavailable", setRipV1: { publicScore: null, score: 88, rank: 3, tier: "B" } },
  ]);
  assert.deepEqual(rows.map(({ name, rank, score, tier }) => ({ name, rank, score, tier })), [
    { name: "First", rank: 1, score: 9.2, tier: "S" },
    { name: "Second", rank: 2, score: 8.1, tier: "A" },
  ]);
  for (const forbidden of ["financialRipV4", "collectorAppeal", "chaseAccessibility", "fetch("]) assert.ok(!distribution.includes(forbidden));
});

test("Overview replaces the old outcome chart and reuses the one cached Set request", () => {
  for (const removed of ["Opening Outcome Range", "normalizedReturnBuckets", "normalizedReturnPercentiles", "Sets represented"]) assert.ok(!distribution.includes(removed));
  assert.ok(distribution.includes("How Sets Rank to Open"));
  assert.ok(lazy.includes("targets={setTargets}"));
  assert.equal((lazy.match(/lens\?lens=sets/g) || []).length, 1);
});

test("Set Pack Economics uses the requested vocabulary and canonical order", () => {
  assert.deepEqual(SET_PACK_COLUMNS.map(([key, label]) => [key, label]), [
    ["productFamilies", "Product Families"], ["products", "Products"], ["packPrice", "Avg Cost / Pack"], ["modelBreakEven", "Expected Value / Pack"], ["modeledReturn", "Modeled Return"], ["typicalOpening", "Typical Opening / Pack"], ["typicalRetention", "Typical Retention"], ["chanceToRecoverCost", "Chance to Recover Cost"], ["entertainmentCost", "Entertainment Cost / Pack"],
  ]);
  assert.ok(setPack.includes("overflow-x-auto"));
  assert.ok(setPack.includes("styles.colSetPackIdentity"));
  assert.ok(!setPack.includes("Break-Even / Pack"));
});

test("Era Pack Economics has the matching vocabulary and order", () => {
  const block = eraPack.slice(eraPack.indexOf("const COLUMNS = ["), eraPack.indexOf("const PUBLIC_ERA_COLUMN_KEYS"));
  const keys = [...block.matchAll(/key: "([^"]+)"/g)].map((match) => match[1]);
  assert.deepEqual(keys, ["eraName", "setCount", "productSkuCount", "meanPackCost", "expectedValue", "modeledReturn", "typicalOpening", "typicalRetention", "chanceToRecover", "entertainmentCost"]);
  assert.ok(block.includes('label: "Expected Value / Pack"'));
  assert.ok(!eraPack.includes("Break-Even"));
});

test("Financial RIP renders persisted Expected Value before the supporting outcomes", () => {
  assert.ok(financial.includes('["Expected Value", "Typical Opening", "Modeled Return", "Chance to Beat Cost"]'));
  assert.ok(financial.includes("metric.modelBreakEven"));
  assert.ok(!financial.includes("metric.typicalOpening /"));
});

test("Product Rankings removes strategy quantities without changing budget rank", () => {
  for (const removed of [">Units<", ">Committed<", "row?.quantity", "row?.actualCommittedCapital", "<Strategy"]) assert.ok(!products.includes(removed));
  assert.ok(products.includes("row?.budgetRank"));
  assert.ok(products.includes("budgetKey"));
});
