const fs = require("fs");
const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");

const ripPageClientPath = path.resolve(__dirname, "RipStatisticsPageClient.jsx");
const historyChartPath = path.resolve(__dirname, "PackValueHistoryChart.jsx");
const rankingConfigPath = path.resolve(__dirname, "../../constants/exploreRankingConfig.js");

test("Set Intelligence Biggest Upside wiring references relative-first score fields and both upside evidence labels", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes('scoreFields: ["relative_biggest_upside_score", "biggest_upside_score"]'));
  assert.ok(source.includes('tierField: "biggest_upside_tier"'));
  assert.ok(source.includes('rankField: "biggest_upside_rank"'));
  assert.ok(source.includes('"Big Hit Upside"'));
  assert.ok(source.includes('"God Pull Upside"'));
});

test("Set Intelligence Average Return wiring prefers relative score fields", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes('"relative_average_return_score"'));
  assert.ok(source.includes('"relative_mean_value_to_cost_score"'));
  assert.ok(source.includes('format: "score"'));
});

test("Performance vs Cost chart uses standardized line labels and drops High-End / Cost", () => {
  const source = fs.readFileSync(historyChartPath, "utf8");

  assert.ok(source.includes('label="Average Return"'));
  assert.ok(source.includes('label="Typical Return"'));
  assert.ok(source.includes('label="Big Hit Upside"'));
  assert.ok(!source.includes('label="God Pull Upside"'));
  assert.ok(!source.includes('name="God Pull Upside"'));
  assert.ok(!source.includes("High-End / Cost"));
  assert.ok(!source.includes("Mean / Cost"));
  assert.ok(!source.includes("Median / Cost"));
});

test("Performance vs Cost metrics include God Pull Upside tile wired to P99 ratio", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes('godPullUpside: "God Pull Upside"'));
  assert.ok(source.includes('label={RIP_COPY.chartStats.godPullUpside}'));
  assert.ok(source.includes('value={formatMultiplier(summary.p99_value_to_cost_ratio, 1)}'));
  assert.ok(source.includes("Simple: Rare monster-hit outcome compared with pack price."));
  assert.ok(source.includes("Expert: P99 outcome vs pack cost."));
});

test("Explore Biggest Upside mode uses blended biggest_upside ranking fields", () => {
  const source = fs.readFileSync(rankingConfigPath, "utf8");

  assert.ok(source.includes('scoreField: "relative_biggest_upside_score"'));
  assert.ok(source.includes('rankField: "biggest_upside_rank"'));
  assert.ok(source.includes('tierField: "biggest_upside_tier"'));
  assert.ok(!source.includes('scoreField: "p95_value_to_cost_ratio"'));
});

test("Explore God Pull Upside mode uses P99 ratio display with P99 ranking fields", () => {
  const source = fs.readFileSync(rankingConfigPath, "utf8");

  assert.ok(source.includes('id: "godPullUpside"'));
  assert.ok(source.includes('label: "God Pull Upside"'));
  assert.ok(source.includes('scoreField: "p99_value_to_cost_ratio"'));
  assert.ok(source.includes('scoreFormat: "ratio"'));
  assert.ok(source.includes('rankField: "p99_value_to_cost_rank"'));
  assert.ok(source.includes('tierField: "p99_value_to_cost_tier"'));
});
