import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  DEFAULT_ERA_SORT,
  ERA_SORT_OPTIONS,
  centsPerDollar,
  distributionRows,
  headlineMetrics,
  isAvailable,
  money,
  projectEraRow,
  ratioAsPercent,
  sortEras,
  valueDescent,
  outcomeRangePositions,
  PERCENTILE_LABELS,
} from "./openingEconomicsSelector.mjs";

// Sources are read with line endings normalized: this tree mixes CRLF and LF,
// and a multi-line anchor silently stops matching the moment it crosses a CRLF.
const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8").replace(/\r\n/g, "\n");

const client = read("./ProductFamilyRankingsClient.jsx");
const overall = read("./OpeningEconomicsOverall.jsx");
const distribution = read("./OpeningEconomicsDistribution.jsx");
const chartFrame = read("./ChartFrame.jsx");
const chartTooltipShell = read("./ChartTooltipShell.jsx");
const chartVisualSystem = read("./chartVisualSystem.mjs");
const eras = read("./OpeningEconomicsEras.jsx");
const page = read("../../app/Explore/page.js");
const server = read("../../lib/explore/openingEconomicsServer.js");

/** Representative published V3 cohort, trimmed to fields the views read. */
const PUBLISHED = {
  status: "available",
  marketDate: "2026-08-27", contractVersion: "pokemon-rip-stats-v3",
  basis: "all_modeled_products_per_pack_equivalent",
  methodology: {version:"hierarchical_product_per_pack_empirical_v1",weightingVersion:"equal-set_equal-family_equal-sku-v1"},
  global: {
    setCount:22,productSkuCount:138,productFamilyCount:8,
    averageCostPerPack:17.8818,averageModelBreakEvenPerPack:6.9946,chanceToRecoverCost:.050652,
    typicalOpeningPerPack:3.5886,typicalRetention:.273823,meanOutcomeRetention:.424644,
    modeledReturnOnSpend:.391157,entertainmentCostShare:.608843,averageEntertainmentCostPerPack:10.8872,
    valuePerPackPercentiles:{p05:1.3853,p25:2.0103,p50:3.5886,p75:7.0103,p95:21.5769,p99:50.8709},
    normalizedReturnPercentiles: {
      p05:.103550,p25:.173094,p50:.273823,p75:.434844,p95:1.007092,p99:2.793935,
    },
  },
  eras: [
    {eraName:"Mega Evolution",setCount:6,averageCostPerPack:11.5962,averageModelBreakEvenPerPack:5.4479,chanceToRecoverCost:.061167,typicalOpeningPerPack:2.8869,typicalRetention:.298182,modeledReturnOnSpend:.469794,entertainmentCostShare:.530206,averageEntertainmentCostPerPack:6.1484},
    {eraName:"Scarlet and Violet",setCount:16,averageCostPerPack:20.2388,averageModelBreakEvenPerPack:7.5746,chanceToRecoverCost:.046709,typicalOpeningPerPack:3.8853,typicalRetention:.260587,modeledReturnOnSpend:.374261,entertainmentCostShare:.625739,averageEntertainmentCostPerPack:12.6642},
  ],
};

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

test("the top-level control offers exactly four lenses in hierarchy order", () => {
  const options = client.slice(client.indexOf('ariaLabel="Ranking view"'));
  const block = options.slice(0, options.indexOf("/>"));
  assert.deepEqual(
    [...block.matchAll(/\{ value: "([a-zA-Z]+)", label: "([^"]+)" \}/g)].map((match) => [match[1], match[2]]),
    [["economics", "Overall"], ["eras", "Eras"], ["sets", "Sets"], ["products", "Products"], ["cards", "Cards"]],
  );
});

test("Overall is the default lens", () => {
  assert.ok(client.includes('const [view, setView] = useState("economics")'));
});

test("four options opt into the scrolling control rather than truncating on mobile", () => {
  const block = client.slice(client.indexOf('ariaLabel="Ranking view"'));
  assert.ok(block.slice(0, block.indexOf("/>")).includes("mobileScroll"));
});

// ---------------------------------------------------------------------------
// Naming: the Products lens says "All Products", never "Overall"
// ---------------------------------------------------------------------------

test("the Products internal tab is renamed All Products", () => {
  assert.ok(client.includes("All Products"));
  assert.ok(client.includes('selectView("allProducts")'));
  assert.ok(client.includes('view === "allProducts"'));
  // The retired product-view key must not survive anywhere in the component.
  assert.ok(!client.includes('"overall"'), "the colliding product view key 'overall' is still present");
});

test("the All Products rename keeps its existing style and data hooks", () => {
  assert.ok(client.includes("data-overall-product-tab"));
  assert.ok(client.includes("productFamilyTabOverallIcon"));
});

// ---------------------------------------------------------------------------
// Overall metrics
// ---------------------------------------------------------------------------

test("Overall renders all six headline metrics from published fields", () => {
  const metrics = headlineMetrics(PUBLISHED.global);
  assert.deepEqual(metrics.map((metric) => metric.label), [
    "Modeled Return on Spend",
    "Average Entertainment Cost",
    "Typical Opening",
    "Chance to Recover Cost",
    "Average Pack Price",
    "Average Model Break-Even",
  ]);
  const byKey = Object.fromEntries(metrics.map((metric) => [metric.key, metric]));
  assert.equal(byKey.modeledReturn.value, "39.1%");
  assert.equal(byKey.entertainmentCost.value, "$10.89");
  assert.equal(byKey.entertainmentCost.secondary, "60.9% of pack spend");
  assert.equal(byKey.typicalOpening.value, "$3.59");
  assert.equal(byKey.typicalOpening.secondary, "27.4% typical retention");
  assert.equal(byKey.chanceToRecover.value, "5.1%");
  assert.equal(byKey.averagePackPrice.value, "$17.88");
  assert.equal(byKey.modelBreakEven.value, "$6.99");
});

test("Typical Opening is read from the published pooled P50, never averaged", () => {
  // The four per-set medians average to 1.92; the published pooled P50 is 1.84.
  // A reader that reconstructed the value would produce the former.
  const metrics = headlineMetrics(PUBLISHED.global);
  const typical = metrics.find((metric) => metric.key === "typicalOpening");
  assert.equal(typical.value, "$3.59");
  assert.notEqual(typical.value, "$1.92");
  assert.match(typical.help, /not an average of each set's median/);
});

test("no view recomputes a statistic in the browser", () => {
  for (const [name, source] of [["Overall", `${overall}\n${distribution}`], ["Eras", eras]]) {
    // Prose may DESCRIBE a median; nothing may COMPUTE one, sum a population,
    // or divide one published aggregate by another to invent a new statistic.
    assert.ok(!/\.reduce\([^)]*\+/.test(source), `${name} sums values client-side`);
    assert.ok(!/Math\.(median|mean)|quantile\(|sort\(\)\s*\[/.test(source), `${name} computes a quantile`);
    assert.ok(!/\/\s*(setCount|eras\.length|rows\.length)/.test(source), `${name} averages across scopes`);
  }
});

test("the interpretation block derives its cents from the live published ratio", () => {
  assert.equal(centsPerDollar(PUBLISHED.global.modeledReturnOnSpend), 39);
  assert.equal(100 - centsPerDollar(PUBLISHED.global.modeledReturnOnSpend), 61);
  assert.ok(distribution.includes("ratioAsPercent(scope.modeledReturnOnSpend)"));
  // No hardcoded figure may stand in for the live value.
  assert.ok(!/\b45¢|\b55¢/.test(overall));
});

test("the pooled distribution exposes all six percentiles", () => {
  const rows = distributionRows(PUBLISHED.global.valuePerPackPercentiles, (value) => money(value));
  assert.deepEqual(rows.map((row) => row.label), ["P05", "P25", "P50", "P75", "P95", "P99"]);
  assert.deepEqual(rows.map((row) => row.display), ["$1.39", "$2.01", "$3.59", "$7.01", "$21.58", "$50.87"]);
});

test("the distribution is not presented as a smooth or normal curve", () => {
  assert.ok(!/gaussian|normal curve|bell/i.test(overall));
});

test("V3 basis and all P01-P99 values drive distribution geometry", () => {
  assert.equal(PUBLISHED.basis, "all_modeled_products_per_pack_equivalent");
  assert.ok(distribution.includes("Array.from({ length: 99 }"));
  assert.ok(distribution.includes('data-percentile-points="99"'));
  assert.ok(distribution.includes("scope.normalizedReturnPercentiles"));
  assert.ok(distribution.includes("scope.valuePerPackPercentiles"));
  assert.ok(!/18\s*\+\s*index\s*\*\s*10/.test(distribution));
  assert.ok(!distribution.includes("resolveLooseBoosterPackArtwork"));
});

test("the active distribution preserves all four global headline metrics", () => {
  assert.ok(overall.includes("<OpeningEconomicsDistribution scope={scope} targets={targets} />"));
  assert.ok(distribution.includes("data-opening-headline-metrics"));
  assert.ok(distribution.includes('scope.modeledReturnOnSpend'));
  assert.ok(distribution.includes('scope.typicalRetention'));
  assert.ok(distribution.includes('scope.chanceToRecoverCost'));
  assert.ok(distribution.includes('scope.averageEntertainmentCostPerPack'));
  for (const label of ["Modeled Return", "Typical Retention", "Chance to Recover", "Entertainment Cost / Pack"]) {
    assert.ok(distribution.includes(label));
  }
});

test("Overall adds the three-value snapshot and one active distribution", () => {
  assert.equal((overall.match(/OpeningEconomicsDistribution scope=/g) || []).length, 1);
  for (const label of ["Average Cost / Pack", "Average Model Break-Even / Pack", "Typical Opening / Pack"]) assert.ok(distribution.includes(label));
  for (const field of ["averageCostPerPack", "averageModelBreakEvenPerPack", "typicalOpeningPerPack"]) assert.ok(distribution.includes(`scope.${field}`));
});

test("Overall reuses the inDex frame, shared visual system, area, glow, and tooltip shell", () => {
  assert.ok(distribution.includes("<ChartFrame"));
  assert.ok(chartFrame.includes("ResizeObserver"));
  assert.ok(distribution.includes("chartVisualSystem.mjs"));
  assert.ok(chartVisualSystem.includes("POSITIVE_VALUE_COLOR"));
  assert.ok(distribution.includes("<Area"));
  assert.ok(distribution.includes("linearGradient"));
  assert.ok(distribution.includes("feGaussianBlur"));
  assert.ok(distribution.includes("<PercentileTooltip"));
  assert.ok(distribution.includes("<ChartTooltipShell"));
  assert.ok(chartTooltipShell.includes("shadow-[0_14px_32px_rgba(0,0,0,0.38)]"));
  assert.ok(!distribution.includes("contentStyle="));
});

test("tooltip explains percentile shares and all published landmarks remain direct", () => {
  assert.ok(distribution.includes("100 - point.percentile"));
  assert.ok(distribution.includes("% of modeled product-opening outcomes"));
  assert.ok(distribution.includes("% finish above"));
  assert.ok(distribution.includes("<ReferenceLine y={1}"));
  for (const field of ["typicalRetention", "meanOutcomeRetention", "typicalOpeningPerPack", "averageModelBreakEvenPerPack"]) assert.ok(distribution.includes(`scope.${field}`));
  assert.ok(distribution.includes('lens === "value" && evAboveP75'));
  assert.ok(distribution.includes("scope.valuePerPackPercentiles?.p75"));
});

test("Overall removes era preview and every dead legacy presentation", () => {
  for (const forbidden of ["EraPreview", "How eras compare", "EconomicEquation", "ValueDescent", "EvInsight", "OutcomeRange", "data-view-era-details"]) assert.ok(!overall.includes(forbidden));
});

test("frontend transport rejects non-V3 available responses", () => {
  assert.ok(server.includes("isOpeningEconomicsV3"));
  assert.ok(server.includes("incompatible_opening_economics_contract"));
  assert.ok(server.includes("all_modeled_products_per_pack_equivalent"));
});

// ---------------------------------------------------------------------------
// Eras
// ---------------------------------------------------------------------------

test("era rows read the published per-era fields", () => {
  const [mega, sv] = PUBLISHED.eras.map(projectEraRow);
  assert.deepEqual(mega, {
    eraName: "Mega Evolution", setCount: 6, meanPackCost: "$11.60", expectedValue: "$5.45",
    typicalOpening: "$2.89", typicalRetention: "29.8%", modeledReturn: "47.0%",
    entertainmentCost: "$6.15", entertainmentCostShare: "53.0%", chanceToRecover: "6.1%",
  });
  assert.equal(sv.modeledReturn, "37.4%");
  assert.equal(sv.typicalOpening, "$3.89");
  assert.equal(sv.entertainmentCost, "$12.66");
});

test("eras default to Modeled Return descending", () => {
  assert.deepEqual(DEFAULT_ERA_SORT, { key: "modeledReturnOnSpend", direction: "desc" });
  const sorted = sortEras(PUBLISHED.eras, DEFAULT_ERA_SORT.key, DEFAULT_ERA_SORT.direction);
  assert.deepEqual(sorted.map((era) => era.eraName), ["Mega Evolution", "Scarlet and Violet"]);
});

test("every documented era sort key resolves a value", () => {
  for (const option of ERA_SORT_OPTIONS) {
    const sorted = sortEras(PUBLISHED.eras, option.value, "desc");
    assert.equal(sorted.length, 2, `${option.value} lost a row`);
  }
});

test("nulls sort last in BOTH directions", () => {
  const withGap = [
    { eraName: "Known", modeledReturnOnSpend: 0.5 },
    { eraName: "Missing", modeledReturnOnSpend: null },
  ];
  for (const direction of ["asc", "desc"]) {
    assert.equal(
      sortEras(withGap, "modeledReturnOnSpend", direction).at(-1).eraName,
      "Missing",
      `null sorted ahead of a value when ${direction}`,
    );
  }
});

test("eras are never scored, ranked or tiered", () => {
  for (const source of [overall, eras]) {
    assert.ok(!/era_?rank|era_?score|era_?tier|eraRank|eraScore|eraTier/i.test(source));
  }
});

// ---------------------------------------------------------------------------
// Missing data
// ---------------------------------------------------------------------------

test("missing values render unavailable, never zero", () => {
  for (const empty of [null, undefined, Number.NaN, Infinity, "", true]) {
    assert.equal(money(empty), null, `money(${String(empty)}) fabricated a value`);
    assert.equal(ratioAsPercent(empty), null, `ratioAsPercent(${String(empty)}) fabricated a value`);
  }
  // A real zero still renders — it is measured, not missing.
  assert.equal(money(0), "$0.00");
  assert.equal(ratioAsPercent(0), "0.0%");
});

test("a negative Entertainment Cost survives rather than being clamped", () => {
  assert.equal(money(-1.25), "-$1.25");
  const metric = headlineMetrics({ ...PUBLISHED.global, averageEntertainmentCostPerPack: -1.25 })
    .find((item) => item.key === "entertainmentCost");
  assert.equal(metric.value, "-$1.25");
});

test("an unavailable contract is not treated as available", () => {
  assert.equal(isAvailable(null), false);
  assert.equal(isAvailable({ status: "unavailable", global: null }), false);
  assert.equal(isAvailable({ status: "available", global: null }), false);
  assert.equal(isAvailable(PUBLISHED), true);
});

test("a missing distribution yields no rows rather than a row of zeros", () => {
  assert.equal(distributionRows(null, money), null);
  assert.equal(distributionRows({ p05: null, p25: null, p50: null, p75: null, p95: null, p99: null }, money), null);
});

// ---------------------------------------------------------------------------
// Independent failure and payload discipline
// ---------------------------------------------------------------------------

test("the opening economics fetch never rejects and never fails the page", () => {
  assert.ok(server.includes("catch"));
  assert.ok(server.includes('status: "unavailable"'));
  // Both lenses render the SAME empty component, so neither can drift into a
  // different failure story than the other.
  assert.ok(overall.includes("data-opening-economics-unavailable"));
  assert.ok(eras.includes("OpeningEconomicsEmpty"));
});

test("opening economics is fetched in parallel with the existing rankings reads", () => {
  const block = page.slice(page.indexOf("await Promise.all(["), page.indexOf("]);"));
  assert.ok(block.includes("getRipStatisticsTargets"));
  assert.ok(block.includes("getOpeningEconomics()"));
});

// ---------------------------------------------------------------------------
// Entitlements
// ---------------------------------------------------------------------------

test("Overall remains public while Era Pack Economics consumes delegated Rankings entitlement", () => {
  assert.ok(!/useRankingsAccess|canViewProductRipIntelligence|onUnlockProductRip|IndexPlus|Premium/i.test(overall));
  assert.ok(eras.includes("canViewRankingsIntelligence"));
  assert.ok(eras.includes("onUnlockProductRip"));
  assert.ok(!eras.includes("useRankingsAccess"));
});

test("the Products lens keeps its existing entitlement gating", () => {
  assert.ok(client.includes("canViewProductRipIntelligence"));
  assert.ok(client.includes("useRankingsAccess"));
  assert.ok(client.includes("onUnlockProductRip"));
});

// ---------------------------------------------------------------------------
// Accessibility
// ---------------------------------------------------------------------------

test("era sort headers expose aria-sort and real buttons", () => {
  assert.ok(eras.includes("aria-sort="));
  assert.ok(eras.includes('scope="col"'));
  assert.ok(eras.includes('scope={identity ? "row" : undefined}'));
  assert.ok(eras.includes('type="button"'));
});

test("the era drilldown to Sets is reachable", () => {
  assert.ok(eras.includes("data-era-drilldown"));
  assert.ok(client.includes('onSelectEras={() => selectView("eras")}'));
  // Selecting an era switches to Sets and scopes it, rather than rendering a
  // second set table inside the Eras lens.
  assert.ok(client.includes('selectView("sets")'));
  assert.ok(client.includes("setSelectedEra(era?.eraName || null)"));
  assert.ok(client.includes("eraFilter={selectedEra}"));
  assert.ok(!eras.includes("ExploreTableClient"), "Eras must not embed a duplicate set table");
});

// ---------------------------------------------------------------------------
// Value descent and the outcome range (this pass)
// ---------------------------------------------------------------------------

test("the descent presents price, break-even and typical as one progression", () => {
  const stages = valueDescent(PUBLISHED.global);
  assert.deepEqual(stages.map((stage) => stage.value), ["$17.88", "$6.99", "$3.59"]);
  // Bar length is the value's share of the pack price, so the collapse is read
  // as distance. The price stage is the full-width reference.
  assert.equal(stages[0].percent, 100);
  assert.ok(stages[1].percent > stages[2].percent);
  assert.ok(stages[2].percent < 25);
  // Break-Even must declare that it IS Expected Value, not a second statistic.
  assert.equal(stages[1].sameAsExpectedValue, true);
});

test("the outcome range places EV to the right of the typical band", () => {
  const range = outcomeRangePositions(PUBLISHED.global.valuePerPackPercentiles, PUBLISHED.global.averageModelBreakEvenPerPack);
  assert.equal(range.scale, "logarithmic");
  const at = Object.fromEntries(range.points.map((point) => [point.key, point.percent]));
  assert.ok(range.expectedValue.percent > at.p50, "EV must plot right of the median");
  assert.ok(range.expectedValue.percent < at.p75, "EV must plot left of the 75th percentile");
  assert.equal(range.expectedValue.display, "$6.99");
  // Ticks ascend and stay inside the axis.
  const ordered = ["p05", "p25", "p50", "p75", "p95", "p99"].map((key) => at[key]);
  assert.deepEqual(ordered, [...ordered].sort((a, b) => a - b));
  assert.equal(Math.round(ordered[0]), 0);
  assert.equal(Math.round(ordered.at(-1)), 100);
});

test("percentiles are named as positions, never as probabilities", () => {
  assert.equal(PERCENTILE_LABELS.p95, "95th percentile");
  assert.equal(PERCENTILE_LABELS.p50, "Typical (median)");
  for (const source of [overall, eras]) {
    assert.ok(!/95% chance|99% chance|90% chance/i.test(source));
  }
});

test("the range is labeled with its scale and carries a text equivalent", () => {
  assert.ok(distribution.includes("logarithmic value axis"));
  assert.ok(distribution.includes("The logarithmic value axis"));
});

test("Modeled Return and Typical Retention are never presented as the same thing", () => {
  const returnPct = ratioAsPercent(PUBLISHED.global.modeledReturnOnSpend);
  const retentionPct = ratioAsPercent(PUBLISHED.global.typicalRetention);
  assert.equal(returnPct, "39.1%");
  assert.equal(retentionPct, "27.4%");
  assert.notEqual(returnPct, retentionPct);
  // Their help text must distinguish median-of-outcomes from aggregate-of-spend.
  assert.match(distribution, /Median of the weighted normalized-return distribution/);
  assert.match(distribution, /Weighted aggregate EV divided by weighted aggregate cost/);
});

test("the recover-cost metric is never relabelled as profit", () => {
  for (const source of [overall, eras]) {
    assert.ok(!/chance to profit/i.test(source));
  }
  assert.ok(distribution.includes("Chance to Recover Cost"));
});

test("entertainment cost language is descriptive, not moralizing", () => {
  assert.ok(!/wasted|bad decision|gambl|you lose/i.test(overall));
  assert.match(distribution, /Modeled purchase cost not returned as gross card value/);
});

test("no accent other than teal is introduced", () => {
  const css = read("./openingEconomics.module.css");
  assert.ok(!css.includes("--ex-amber"), "the amber token must not be used as an accent");
  assert.ok(!/#f[0-9a-f]{2}[0-9a-f]{0,3}\b|yellow|gold/i.test(css));
  assert.ok(css.includes("--ex-teal"));
});

test("the loading state uses stable skeleton dimensions", () => {
  assert.ok(overall.includes("OpeningEconomicsSkeleton"));
  assert.ok(overall.includes('aria-busy="true"'));
  const css = read("./openingEconomics.module.css");
  assert.ok(css.includes("prefers-reduced-motion"));
});

test("a stale snapshot reads as absence and a failed request reads as failure", () => {
  // Two different reasons must not produce the same sentence.
  assert.match(overall, /request_failed/);
  assert.match(overall, /does not yet contain aggregate/);
  assert.match(overall, /could not be loaded/);
});
