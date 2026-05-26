const fs = require("fs");
const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");

const ripPageClientPath = path.resolve(__dirname, "RipStatisticsPageClient.jsx");
const historyChartPath = path.resolve(__dirname, "PackValueHistoryChart.jsx");
const rankingConfigPath = path.resolve(__dirname, "../../constants/exploreRankingConfig.js");
const pullRateAssumptionsCardPath = path.resolve(__dirname, "PullRateAssumptionsCard.jsx");

function extractFunctionSource(source, functionName) {
  const marker = `function ${functionName}(`;
  const start = source.indexOf(marker);
  if (start === -1) {
    throw new Error(`Could not find function ${functionName}`);
  }

  const openBrace = source.indexOf("{", start);
  if (openBrace === -1) {
    throw new Error(`Could not find opening brace for ${functionName}`);
  }

  let depth = 0;
  for (let i = openBrace; i < source.length; i += 1) {
    if (source[i] === "{") {
      depth += 1;
    } else if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) {
        return source.slice(start, i + 1);
      }
    }
  }

  throw new Error(`Could not find closing brace for ${functionName}`);
}

function loadOddsFormatter() {
  const source = fs.readFileSync(pullRateAssumptionsCardPath, "utf8");
  const toFiniteNumberSource = extractFunctionSource(source, "toFiniteNumber");
  const formatOddsDenominatorSource = extractFunctionSource(source, "formatOddsDenominator");
  const factory = new Function(
    `${toFiniteNumberSource}\n${formatOddsDenominatorSource}\nreturn { formatOddsDenominator };`,
  );

  return factory().formatOddsDenominator;
}

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

test("Pack Breakdown supports modeled outcome states for slot-schema sets", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes('packBreakdownDisplay?.mode === "modeled_outcome_states"'));
  assert.ok(source.includes("<ModeledOutcomeBars display={packBreakdownDisplay} />"));
  assert.ok(source.includes("Modeled outcome buckets show how often each value-bearing bucket was selected by the simulator under the current slot-based assumptions."));
  assert.ok(source.includes("These states reflect the simulator's slot-based assumptions, not official Pokemon collation guarantees."));
  assert.ok(source.includes("Show all modeled states"));
  assert.ok(source.includes("display?.limitation_note"));
});

test("Pull-rate odds denominator shows one decimal for non-integer values under 100", () => {
  const formatOddsDenominator = loadOddsFormatter();

  assert.equal(formatOddsDenominator(15.333), "1 in 15.3 packs");
  assert.equal(formatOddsDenominator(54.393), "1 in 54.4 packs");
  assert.equal(formatOddsDenominator(41.456), "1 in 41.5 packs");
});

test("Pull-rate odds denominator keeps integers whole and rounds large values to whole numbers", () => {
  const formatOddsDenominator = loadOddsFormatter();

  assert.equal(formatOddsDenominator(72), "1 in 72 packs");
  assert.equal(formatOddsDenominator(1090), "1 in 1,090 packs");
});

test("Pull Rates panel still states that the assumptions are the ones used by the simulation", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes("Modeled rarity frequency and specific-card odds used by this simulation."));
  assert.ok(source.includes("These are modeled estimates, not official Pokémon odds."));
});
