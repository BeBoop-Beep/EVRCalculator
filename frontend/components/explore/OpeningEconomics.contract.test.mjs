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
} from "./openingEconomicsSelector.mjs";

// Sources are read with line endings normalized: this tree mixes CRLF and LF,
// and a multi-line anchor silently stops matching the moment it crosses a CRLF.
const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8").replace(/\r\n/g, "\n");

const client = read("./ProductFamilyRankingsClient.jsx");
const overall = read("./OpeningEconomicsOverall.jsx");
const eras = read("./OpeningEconomicsEras.jsx");
const page = read("../../app/Explore/page.js");
const server = read("../../lib/explore/openingEconomicsServer.js");

/** The published 2026-08-26 cohort, trimmed to the fields the views read. */
const PUBLISHED = {
  status: "available",
  marketDate: "2026-08-26",
  weightingMode: "equal_set_weight",
  productFamily: "loose_booster_pack",
  global: {
    setCount: 22,
    meanPackCost: 11.896363636363638,
    expectedValue: 5.404382489090909,
    chanceToBeatCost: 0.07195186363636363,
    typicalOpening: { value: 1.84, retention: 0.19812206572769955, quantile: 0.5 },
    modeledReturnOnSpend: 0.4542886090478374,
    entertainmentCostShare: 0.5457113909521626,
    expectedEntertainmentCost: 6.491981147272727,
    rawDistribution: { p05: 1.25, p25: 1.54, p50: 1.84, p75: 2.88, p95: 15.94, p99: 60.39 },
    normalizedReturnDistribution: {
      p05: 0.08785529715762275, p25: 0.13649425287356323, p50: 0.19812206572769955,
      p75: 0.28648648648648645, p95: 1.4180180180180182, p99: 4.710488651581117,
    },
  },
  eras: [
    { eraName: "Mega Evolution", setCount: 6, meanPackCost: 8.391666666666667,
      expectedValue: 4.5461129499999995, chanceToBeatCost: 0.0635595,
      typicalOpening: { value: 1.71, retention: 0.2433392539964476 },
      modeledReturnOnSpend: 0.541741364448858, entertainmentCostShare: 0.458258635551142,
      expectedEntertainmentCost: 3.8455537166666667 },
    { eraName: "Scarlet and Violet", setCount: 16, meanPackCost: 13.210625,
      expectedValue: 5.726233566250015, chanceToBeatCost: 0.075099,
      typicalOpening: { value: 1.87, retention: 0.1758849557522124 },
      modeledReturnOnSpend: 0.4334566734162843, entertainmentCostShare: 0.5665433265837156,
      expectedEntertainmentCost: 7.484391433749999 },
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
    [["economics", "Overall"], ["eras", "Eras"], ["sets", "Sets"], ["products", "Products"]],
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
  assert.equal(byKey.modeledReturn.value, "45.4%");
  assert.equal(byKey.entertainmentCost.value, "$6.49");
  assert.equal(byKey.entertainmentCost.secondary, "54.6% of pack spend");
  assert.equal(byKey.typicalOpening.value, "$1.84");
  assert.equal(byKey.typicalOpening.secondary, "19.8% typical retention");
  assert.equal(byKey.chanceToRecover.value, "7.2%");
  assert.equal(byKey.averagePackPrice.value, "$11.90");
  assert.equal(byKey.modelBreakEven.value, "$5.40");
});

test("Typical Opening is read from the published pooled P50, never averaged", () => {
  // The four per-set medians average to 1.92; the published pooled P50 is 1.84.
  // A reader that reconstructed the value would produce the former.
  const metrics = headlineMetrics(PUBLISHED.global);
  const typical = metrics.find((metric) => metric.key === "typicalOpening");
  assert.equal(typical.value, "$1.84");
  assert.notEqual(typical.value, "$1.92");
  assert.match(typical.help, /not an average of each set's median/);
});

test("no view recomputes a statistic in the browser", () => {
  for (const [name, source] of [["Overall", overall], ["Eras", eras]]) {
    // Prose may DESCRIBE a median; nothing may COMPUTE one, sum a population,
    // or divide one published aggregate by another to invent a new statistic.
    assert.ok(!/\.reduce\([^)]*\+/.test(source), `${name} sums values client-side`);
    assert.ok(!/Math\.(median|mean)|quantile\(|sort\(\)\s*\[/.test(source), `${name} computes a quantile`);
    assert.ok(!/\/\s*(setCount|eras\.length|rows\.length)/.test(source), `${name} averages across scopes`);
  }
});

test("the interpretation block derives its cents from the live published ratio", () => {
  assert.equal(centsPerDollar(PUBLISHED.global.modeledReturnOnSpend), 45);
  assert.equal(100 - centsPerDollar(PUBLISHED.global.modeledReturnOnSpend), 55);
  assert.ok(overall.includes("centsPerDollar(scope.modeledReturnOnSpend)"));
  // No hardcoded figure may stand in for the live value.
  assert.ok(!/\b45¢|\b55¢/.test(overall));
});

test("the pooled distribution exposes all six percentiles", () => {
  const rows = distributionRows(PUBLISHED.global.rawDistribution, (value) => money(value));
  assert.deepEqual(rows.map((row) => row.label), ["P05", "P25", "P50", "P75", "P95", "P99"]);
  assert.deepEqual(rows.map((row) => row.display), ["$1.25", "$1.54", "$1.84", "$2.88", "$15.94", "$60.39"]);
});

test("the distribution is not presented as a smooth or normal curve", () => {
  assert.ok(!/gaussian|normal curve|bell/i.test(overall));
});

// ---------------------------------------------------------------------------
// Eras
// ---------------------------------------------------------------------------

test("era rows read the published per-era fields", () => {
  const [mega, sv] = PUBLISHED.eras.map(projectEraRow);
  assert.deepEqual(mega, {
    eraName: "Mega Evolution", setCount: 6, meanPackCost: "$8.39", expectedValue: "$4.55",
    typicalOpening: "$1.71", typicalRetention: "24.3%", modeledReturn: "54.2%",
    entertainmentCost: "$3.85", entertainmentCostShare: "45.8%", chanceToRecover: "6.4%",
  });
  assert.equal(sv.modeledReturn, "43.3%");
  assert.equal(sv.typicalOpening, "$1.87");
  assert.equal(sv.entertainmentCost, "$7.48");
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
  const metric = headlineMetrics({ ...PUBLISHED.global, expectedEntertainmentCost: -1.25 })
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
  assert.ok(overall.includes("data-opening-economics-unavailable"));
  assert.ok(eras.includes("data-opening-economics-eras-unavailable"));
});

test("opening economics is fetched in parallel with the existing rankings reads", () => {
  const block = page.slice(page.indexOf("await Promise.all(["), page.indexOf("]);"));
  assert.ok(block.includes("getRipStatisticsTargets"));
  assert.ok(block.includes("getOpeningEconomics()"));
});

// ---------------------------------------------------------------------------
// Entitlements
// ---------------------------------------------------------------------------

test("Overall and Eras are public and resolve no entitlement", () => {
  for (const source of [overall, eras]) {
    assert.ok(!/useRankingsAccess|canViewProductRipIntelligence|onUnlockProductRip|IndexPlus|Premium/i.test(source));
  }
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
  assert.ok(eras.includes('scope="row"'));
  assert.ok(eras.includes('type="button"'));
});

test("the era drilldown to Sets is reachable", () => {
  assert.ok(eras.includes("data-era-drilldown"));
  assert.ok(client.includes('onSelectSets={() => selectView("sets")}'));
  assert.ok(overall.includes("data-view-era-details"));
  assert.ok(client.includes('onSelectEras={() => selectView("eras")}'));
});
