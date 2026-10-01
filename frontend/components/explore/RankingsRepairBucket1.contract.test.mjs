import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { readSetRipLandscape } from "./setRipLandscapeSelector.mjs";
import { SET_PACK_COLUMNS } from "./setPackMetricsSelector.mjs";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const distribution = read("./OpeningEconomicsDistribution.jsx");
const setPack = read("./SetPackMetrics.jsx");
const eraPack = read("./OpeningEconomicsEras.jsx");
const financial = read("./BenchmarkEntityScoreTable.jsx");
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

test("Overview replaces the old outcome chart and uses the public Set authority", () => {
  for (const removed of ["Opening Outcome Range", "normalizedReturnBuckets", "normalizedReturnPercentiles", "Sets represented"]) assert.ok(!distribution.includes(removed));
  assert.ok(distribution.includes("FinancialRipHistoryChart"));
  assert.ok(lazy.includes('readPublicRankingsHeadlines("set"'));
});

test("Set Pack Economics uses the requested vocabulary and canonical order", () => {
  assert.deepEqual(SET_PACK_COLUMNS.map(([key, label]) => [key, label]), [
    ["productFamilyCount", "Families"], ["productCount", "Products"], ["averagePackCostPerPack", "Avg Pack Cost"], ["expectedValuePerPack", "EV / Pack"], ["modeledReturnOnSpend", "Modeled Return"], ["chanceToRecoverCost", "Recover Cost"], ["entertainmentCostPerPack", "Entertainment Cost"], ["bestOpenPrice", "Best-Open Price"],
  ]);
  assert.ok(setPack.includes("overflow-x-auto"));
  assert.ok(setPack.includes("styles.colPackEconomicsIdentity"));
  for (const removed of ["Break-Even / Pack", "Typical Opening", "Typical Retention"]) assert.ok(!setPack.includes(removed));
});

test("Era Pack Economics uses the approved narrow current vocabulary", () => {
  const block = eraPack.slice(eraPack.indexOf("const COLUMNS = ["), eraPack.indexOf("const PUBLIC_ERA_COLUMN_KEYS"));
  const keys = [...block.matchAll(/key: "([^"]+)"/g)].map((match) => match[1]);
  assert.deepEqual(keys, ["eraName", "setCount", "productSkuCount", "meanPackCost", "expectedValue", "modeledReturn", "chanceToRecover", "entertainmentCost"]);
  assert.ok(block.includes('label: "Expected Value / Pack"'));
  assert.ok(!eraPack.includes("Break-Even"));
});

test("Financial RIP column renders through the unified benchmark component score", () => {
  assert.ok(financial.includes("SCORE_COLUMNS"));
  assert.ok(financial.includes("RankingsBenchmarkComponentScore"));
  assert.ok(!financial.includes("metric.typicalOpening /"));
});

test("Product Rankings removes strategy quantities and uses published full-market rank", () => {
  for (const removed of [">Units<", ">Committed<", "row?.quantity", "row?.actualCommittedCapital", "<Strategy"]) assert.ok(!products.includes(removed));
  assert.ok(products.includes("row.rank"));
  assert.ok(products.includes("row.cohortSize"));
});
