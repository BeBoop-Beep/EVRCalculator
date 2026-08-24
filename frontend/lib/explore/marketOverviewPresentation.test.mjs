// Market Overview presentation: selection, clipping and formatting only.
//
// The recurring risk this file guards is a frontend that quietly INVENTS a
// market number — recomputing a percentage off chart points, substituting
// Since Tracking for an unavailable 6M, or charting basket dollars on the
// index axis. Every assertion below ties a rendered concept back to the exact
// backend field it must come from.

import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  MARKET_DIMENSION_LABELS,
  MARKET_OVERVIEW_GROUPS,
  MARKET_OVERVIEW_HELP,
  buildCoverageSummary,
  buildMarketPerformanceSeries,
  buildMarketWindowOptions,
  changeDirection,
  describeChange,
  describeUnavailableWindow,
  formatBasketValue,
  formatChangePercent,
  formatIndexValue,
  getMarketChange,
  getPricePerformanceChange,
  getTrackedValueChange,
  isMarketWindowAvailable,
  resolveDefaultMarketWindow,
  resolveMarketOverview,
} from "./marketOverviewPresentation.mjs";

const change = (percent, startDate, endDate) => ({ available: true, percent, startDate, endDate, targetStartDate: startDate, coverage: "full" });
const missing = (endDate, targetStartDate) => ({ available: false, percent: null, startDate: null, endDate, targetStartDate, coverage: "unavailable" });

// Deliberately NOT the production numbers: a fixture that echoed the live
// snapshot could not tell "read from the payload" apart from "hardcoded".
const RAW_TREND = [
  ["2024-01-01", 100],
  ["2024-01-02", 101],
  ["2024-01-03", 99.5],
  ["2024-01-04", 102.25],
];
const CHASE_TREND = [
  ["2024-01-01", 100],
  ["2024-01-02", 98],
  ["2024-01-03", 97],
  ["2024-01-04", 96.5],
];

const SNAPSHOT = {
  marketOverview: {
    contractVersion: "pokemon-market-overview-v1",
    marketDate: "2024-01-04",
    coverage: { eligibleSetCount: 3, rawCardCount: 512, chaseCardCount: 30, cohortFingerprint: "fp" },
    raw: {
      basketValue: 8123.45,
      indexValue: 102.25,
      historyStartDate: "2024-01-01",
      trend: RAW_TREND,
      // Tracked Value moved MORE than price performance: a set joined the
      // universe inside these windows. The two must never be interchangeable.
      basketChanges: {
        "1D": change(3.5, "2024-01-03", "2024-01-04"),
        "7D": change(9.75, "2024-01-01", "2024-01-04"),
        "30D": change(9.75, "2024-01-01", "2024-01-04"),
        "3M": missing("2024-01-04", "2023-10-07"),
        "6M": missing("2024-01-04", "2023-07-09"),
        "1Y": missing("2024-01-04", "2023-01-06"),
        SinceTracking: change(9.75, "2024-01-01", "2024-01-04"),
      },
      changes: {
        "1D": change(2.7638, "2024-01-03", "2024-01-04"),
        "7D": change(2.25, "2024-01-01", "2024-01-04"),
        "30D": change(2.25, "2024-01-01", "2024-01-04"),
        "3M": missing("2024-01-04", "2023-10-07"),
        "6M": missing("2024-01-04", "2023-07-09"),
        "1Y": missing("2024-01-04", "2023-01-06"),
        SinceTracking: change(2.25, "2024-01-01", "2024-01-04"),
      },
    },
    topChase: {
      basketValue: 4011.1,
      indexValue: 96.5,
      historyStartDate: "2024-01-01",
      trend: CHASE_TREND,
      basketChanges: {
        "1D": change(1.25, "2024-01-03", "2024-01-04"),
        "7D": change(4.5, "2024-01-01", "2024-01-04"),
        "30D": change(4.5, "2024-01-01", "2024-01-04"),
        "3M": missing("2024-01-04", "2023-10-07"),
        "6M": missing("2024-01-04", "2023-07-09"),
        "1Y": missing("2024-01-04", "2023-01-06"),
        SinceTracking: change(4.5, "2024-01-01", "2024-01-04"),
      },
      changes: {
        "1D": change(-0.5154, "2024-01-03", "2024-01-04"),
        "7D": change(-3.5, "2024-01-01", "2024-01-04"),
        "30D": change(-3.5, "2024-01-01", "2024-01-04"),
        "3M": missing("2024-01-04", "2023-10-07"),
        "6M": missing("2024-01-04", "2023-07-09"),
        "1Y": missing("2024-01-04", "2023-01-06"),
        SinceTracking: change(-3.5, "2024-01-01", "2024-01-04"),
      },
    },
  },
  sets: [],
  meta: {},
};

const overview = resolveMarketOverview(SNAPSHOT);

const SEALED_TREND = [
  ["2024-01-01", 100],
  ["2024-01-02", 100],
  ["2024-01-03", 104],
  ["2024-01-04", 105.5],
];

const snapshotWithSealed = structuredClone(SNAPSHOT);
snapshotWithSealed.marketOverview.coverage.sealedProductCount = 42;
snapshotWithSealed.marketOverview.sealedMarket = {
  basketValue: 12345.67,
  indexValue: 105.5,
  historyStartDate: "2024-01-01",
  trend: SEALED_TREND,
  changes: {
    "1D": change(1.4423, "2024-01-03", "2024-01-04"),
    "7D": change(5.5, "2024-01-01", "2024-01-04"),
    "30D": change(5.5, "2024-01-01", "2024-01-04"),
    "3M": missing("2024-01-04", "2023-10-07"),
    "6M": missing("2024-01-04", "2023-07-09"),
    "1Y": missing("2024-01-04", "2023-01-06"),
    SinceTracking: change(5.5, "2024-01-01", "2024-01-04"),
  },
};
const sealedOverview = resolveMarketOverview(snapshotWithSealed);

test("both published families resolve, in Raw then Top 10 Chase order", () => {
  assert.deepEqual(overview.families.map((family) => family.key), ["raw", "topChase"]);
  assert.deepEqual(overview.families.map((family) => family.label), ["Raw Card Market", "Top 10 Chase Market"]);
});

test("an additive Sealed Market family is normalized from prepared backend values", () => {
  assert.deepEqual(sealedOverview.families.map((family) => family.key), ["raw", "topChase", "sealedMarket"]);
  const sealed = sealedOverview.families[2];
  assert.equal(sealed.label, "Sealed Market");
  assert.equal(sealed.basketValue, 12345.67);
  assert.equal(sealed.indexValue, 105.5);
  assert.equal(getMarketChange(sealed, "7D").percent, 5.5);
  assert.equal(sealedOverview.coverage.sealedProductCount, 42);
});

test("the performance model contains all three prepared index series", () => {
  const model = buildMarketPerformanceSeries(sealedOverview, "7D");
  assert.equal(model.available, true);
  assert.deepEqual(model.series.map((entry) => entry.key), ["raw", "topChase", "sealedMarket"]);
  assert.deepEqual(model.series[2].values, SEALED_TREND.map(([, value]) => value));
});

test("Sealed availability participates in the shared timeframe resolution", () => {
  assert.equal(isMarketWindowAvailable(sealedOverview, "7D"), true);
  assert.equal(isMarketWindowAvailable(sealedOverview, "1Y"), false);
});

test("a snapshot with no marketOverview resolves to null rather than an empty market", () => {
  assert.equal(resolveMarketOverview({ sets: [], meta: {} }), null);
  assert.equal(resolveMarketOverview({ marketOverview: null }), null);
  assert.equal(resolveMarketOverview(null), null);
});

test("basket value and index are separate values read from separate fields", () => {
  const raw = overview.families[0];
  assert.equal(raw.basketValue, 8123.45);
  assert.equal(raw.indexValue, 102.25);
  assert.equal(formatBasketValue(raw.basketValue), "$8,123.45");
  assert.equal(formatIndexValue(raw.indexValue), "102.25");
  assert.notEqual(formatBasketValue(raw.basketValue), formatIndexValue(raw.indexValue));
});

test("1D / 7D / 30D / Since Tracking read the backend change objects verbatim", () => {
  const raw = overview.families[0];
  const chase = overview.families[1];
  assert.equal(getMarketChange(raw, "1D").percent, 2.7638);
  assert.equal(getMarketChange(raw, "7D").percent, 2.25);
  assert.equal(getMarketChange(raw, "30D").percent, 2.25);
  // "All" is the display name; the backend key is SinceTracking.
  assert.equal(getMarketChange(raw, "All").percent, 2.25);
  assert.equal(getMarketChange(chase, "1D").percent, -0.5154);
  assert.equal(formatChangePercent(getMarketChange(raw, "1D")), "+2.76%");
  assert.equal(formatChangePercent(getMarketChange(chase, "1D")), "−0.52%");
});

test("an unavailable window yields no percentage and no substituted window", () => {
  for (const key of ["3M", "6M", "1Y"]) {
    assert.equal(isMarketWindowAvailable(overview, key), false, `${key} must read unavailable`);
    for (const family of overview.families) {
      const entry = getMarketChange(family, key);
      assert.equal(entry.available, false);
      assert.equal(entry.percent, null);
      assert.equal(formatChangePercent(entry), "—");
      assert.equal(changeDirection(entry), "unavailable");
    }
    const model = buildMarketPerformanceSeries(overview, key);
    assert.equal(model.available, false);
    assert.deepEqual(model.dates, []);
    assert.deepEqual(model.series, []);
  }
  assert.equal(describeUnavailableWindow("6M"), "6M — not enough history");
});

test("the timeframe selector offers every backend window with its declared availability", () => {
  assert.deepEqual(
    buildMarketWindowOptions(overview).map((entry) => [entry.key, entry.available]),
    [["1D", true], ["7D", true], ["30D", true], ["3M", false], ["6M", false], ["1Y", false], ["All", true]]
  );
  assert.equal(resolveDefaultMarketWindow(overview, "30D"), "30D");
  assert.equal(resolveDefaultMarketWindow(overview, "1Y"), "1D");
});

test("the dual-series model charts raw.trend and topChase.trend as index values", () => {
  const model = buildMarketPerformanceSeries(overview, "All");
  assert.equal(model.available, true);
  assert.deepEqual(model.series.map((entry) => entry.key), ["raw", "topChase"]);
  assert.deepEqual(model.series[0].values, RAW_TREND.map(([, value]) => value));
  assert.deepEqual(model.series[1].values, CHASE_TREND.map(([, value]) => value));
  // Index values, never basket dollars.
  for (const entry of model.series) {
    for (const value of entry.values) {
      assert.ok(value < 1000, "the chart axis must carry index values, not basket dollars");
    }
  }
  assert.notEqual(model.series[0].color, model.series[1].color);
});

test("the charted span is clipped to the backend window's start and end dates", () => {
  const model = buildMarketPerformanceSeries(overview, "1D");
  const backend = getMarketChange(overview.families[0], "1D");
  assert.equal(model.startDate, backend.startDate);
  assert.equal(model.endDate, backend.endDate);
  assert.deepEqual(model.dates, ["2024-01-03", "2024-01-04"]);
  assert.deepEqual(model.series[0].values, [99.5, 102.25]);
  assert.deepEqual(model.series[1].values, [97, 96.5]);
});

test("change direction is described in words, never carried by color alone", () => {
  assert.match(describeChange("Raw Card Market", "1D", getMarketChange(overview.families[0], "1D")), /up 2\.76 percent/);
  assert.match(describeChange("Top 10 Chase Market", "1D", getMarketChange(overview.families[1], "1D")), /down 0\.52 percent/);
  assert.match(describeChange("Raw Card Market", "6M", getMarketChange(overview.families[0], "6M")), /not enough history/);
});

test("the coverage summary reads the published coverage counts", () => {
  assert.deepEqual(buildCoverageSummary(overview), [
    "As of Jan 4, 2024",
    "3 tracked sets",
    "512 raw cards",
    "30 chase cards",
  ]);
  assert.deepEqual(buildCoverageSummary(null), []);
});

test("help text names the tracked basket honestly and never as market capitalization", () => {
  const copy = Object.values(MARKET_OVERVIEW_HELP).join(" ");
  assert.ok(copy.includes("This is not market capitalization."));
  // Tracked Value must explain that the tracked total moves when sets join.
  assert.match(MARKET_OVERVIEW_HELP.trackedValue, /sets enter or leave the tracked universe/i);
  assert.match(MARKET_OVERVIEW_HELP.trackedValueChange, /current continuous tracking segment/i);
  // The index must be disclaimed as a base-100 index, not a rating.
  assert.match(MARKET_OVERVIEW_HELP.index, /not a score/i);
  assert.match(MARKET_OVERVIEW_HELP.index, /base 100/i);
  assert.match(MARKET_OVERVIEW_HELP.index, /chain-link/i);
  assert.match(MARKET_OVERVIEW_HELP.index, /after a set enters, its later price movement affects the index/i);
  // "market cap" appears only inside the explicit disclaimer.
  assert.doesNotMatch(copy.replace(/This is not market capitalization\./g, ""), /market cap/i);
});

// -- no hardcoded authority ------------------------------------------------

const here = path.dirname(fileURLToPath(import.meta.url));
const PRESENTATION_SOURCES = [
  path.resolve(here, "marketOverviewPresentation.mjs"),
  path.resolve(here, "../../components/explore/PokemonMarketOverview.jsx"),
  path.resolve(here, "../../components/explore/PokemonMarketPerformance.jsx"),
  path.resolve(here, "../../components/explore/MarketPerformanceChart.jsx"),
  path.resolve(here, "../../components/explore/MarketOverviewWindowSelector.jsx"),
  path.resolve(here, "../../app/Market/page.js"),
];

test("no production market figure is hardcoded anywhere in the presentation layer", () => {
  // Live-snapshot authority values. If any of these appear as literals, some
  // surface stopped reading the payload.
  const forbidden = [
    /\bAug 17\b/, /Aug\s*17,\s*2026/, /2026-08-17/,
    /\b4,?372\b/, /\b220\b/, /\b39,?696(\.03)?\b/, /\b27,?287(\.81)?\b/, /\b27,?288\b/,
    /\b101\.9\d/, /\b98\.7\d/,
  ];
  // "22 eligible sets" needs a narrower probe than the bare number 22, which
  // legitimately appears in colors and geometry.
  const forbiddenCoverage = [/22\s*(tracked|eligible)\s*sets/i, /eligibleSetCount\s*[:=]\s*22/];

  for (const file of PRESENTATION_SOURCES) {
    const source = fs.readFileSync(file, "utf8");
    for (const pattern of [...forbidden, ...forbiddenCoverage]) {
      assert.doesNotMatch(source, pattern, `${path.basename(file)} must not hardcode ${pattern}`);
    }
  }
});

test("no user-facing Market Overview copy calls the basket a market cap", () => {
  for (const file of PRESENTATION_SOURCES) {
    const source = fs.readFileSync(file, "utf8");
    // The single permitted occurrence is the explicit disclaimer.
    const withoutDisclaimer = source.replace(/This is not market capitalization\./g, "");
    assert.doesNotMatch(withoutDisclaimer, /market cap/i, `${path.basename(file)} must not describe the basket as market cap`);
    assert.doesNotMatch(source, /total Pok[eé]mon market value/i);
  }
});

test("the Market page never uses investment-judgment language", () => {
  const forbidden = /\b(bullish|bearish|cooling|under pressure|strong market|weak market|overvalued|undervalued)\b/i;
  for (const file of PRESENTATION_SOURCES) {
    assert.doesNotMatch(fs.readFileSync(file, "utf8"), forbidden, path.basename(file));
  }
});


// -- Tracked Value vs. Price Performance -----------------------------------

test("normalization preserves basketChanges alongside changes", () => {
  for (const family of overview.families) {
    assert.ok(family.basketChanges, "every family must carry normalized basketChanges");
    assert.deepEqual(Object.keys(family.basketChanges).sort(), Object.keys(family.changes).sort());
  }
});

test("the two dimensions read different published series", () => {
  const raw = overview.families[0];
  // Tracked Value comes from basketChanges...
  assert.equal(getTrackedValueChange(raw, "All").percent, 9.75);
  assert.equal(getTrackedValueChange(raw, "All"), raw.basketChanges.SinceTracking);
  // ...and Price Performance from changes. Same window, different numbers.
  assert.equal(getPricePerformanceChange(raw, "All").percent, 2.25);
  assert.equal(getPricePerformanceChange(raw, "All"), raw.changes.SinceTracking);
  assert.notEqual(getTrackedValueChange(raw, "All").percent, getPricePerformanceChange(raw, "All").percent);

  const chase = overview.families[1];
  assert.equal(getTrackedValueChange(chase, "All").percent, 4.5);
  assert.equal(getPricePerformanceChange(chase, "All").percent, -3.5);
  // The tracked basket grew while price performance fell — the exact case the
  // two-dimension split exists to express.
  assert.ok(getTrackedValueChange(chase, "All").percent > 0);
  assert.ok(getPricePerformanceChange(chase, "All").percent < 0);
});

test("getMarketChange remains the price-performance helper for existing callers", () => {
  for (const family of overview.families) {
    for (const key of ["1D", "7D", "30D", "All"]) {
      assert.equal(getMarketChange(family, key), getPricePerformanceChange(family, key));
      assert.notEqual(getMarketChange(family, key), getTrackedValueChange(family, key));
    }
  }
});

test("a snapshot published before the extension reports Tracked Value as unavailable, never invented", () => {
  const legacy = resolveMarketOverview({
    marketOverview: {
      marketDate: "2024-01-04",
      coverage: {},
      raw: { basketValue: 8123.45, indexValue: 102.25, historyStartDate: "2024-01-01", trend: RAW_TREND, changes: { SinceTracking: change(2.25, "2024-01-01", "2024-01-04") } },
      topChase: { basketValue: 4011.1, indexValue: 96.5, historyStartDate: "2024-01-01", trend: CHASE_TREND, changes: { SinceTracking: change(-3.5, "2024-01-01", "2024-01-04") } },
    },
  });
  for (const family of legacy.families) {
    assert.deepEqual(family.basketChanges, {});
    assert.equal(getTrackedValueChange(family, "All"), null);
    // Price performance is untouched by the missing field.
    assert.ok(getPricePerformanceChange(family, "All").available);
  }
});

test("the accessible description names which dimension it is speaking about", () => {
  const raw = overview.families[0];
  assert.equal(
    describeChange(raw.label, "Since Tracking", getTrackedValueChange(raw, "All"), { dimension: MARKET_DIMENSION_LABELS.trackedValue }),
    "Raw Card Market, Tracked Value, Since Tracking: up 9.75 percent."
  );
  assert.equal(
    describeChange(raw.label, "Since Tracking", getPricePerformanceChange(raw, "All"), { dimension: MARKET_DIMENSION_LABELS.pricePerformance }),
    "Raw Card Market, Price Performance, Since Tracking: up 2.25 percent."
  );
  // Without a dimension the original wording is unchanged.
  assert.equal(
    describeChange(raw.label, "30D", getPricePerformanceChange(raw, "30D")),
    "Raw Card Market, 30D: up 2.25 percent."
  );
});

test("the chart model still reads the index trend only, never basket dollars", () => {
  const model = buildMarketPerformanceSeries(overview, "All");
  assert.deepEqual(model.series[0].values, RAW_TREND.map(([, value]) => value));
  assert.deepEqual(model.series[1].values, CHASE_TREND.map(([, value]) => value));
  // The change attached to each series is the price-performance one.
  assert.equal(model.series[0].change, overview.families[0].changes.SinceTracking);
  assert.notEqual(model.series[0].change, overview.families[0].basketChanges.SinceTracking);
});

test("the two column-group headings are the locked terminology", () => {
  assert.equal(MARKET_OVERVIEW_GROUPS.trackedValue, "Tracked Market Value");
  assert.equal(MARKET_OVERVIEW_GROUPS.pricePerformance, "Price Performance");
  assert.equal(MARKET_DIMENSION_LABELS.trackedValue, "Tracked Value");
  assert.equal(MARKET_DIMENSION_LABELS.pricePerformance, "Price Performance");
});

test("no frontend source re-derives a basket percentage", () => {
  // The published basketChanges are authoritative. A quotient of two basket
  // values anywhere in the presentation layer would be a frontend analytic.
  const forbidden = [
    /basketValue\s*\//,
    /firstBasket|currentBasket/i,
    /basketChanges\s*=\s*[^;]*[-+*/]/,
  ];
  for (const file of PRESENTATION_SOURCES) {
    const source = fs.readFileSync(file, "utf8");
    for (const pattern of forbidden) {
      assert.doesNotMatch(source, pattern, `${path.basename(file)} must not compute a basket change`);
    }
  }
});
