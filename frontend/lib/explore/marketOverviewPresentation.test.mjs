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

test("both published families resolve, in Raw then Top 10 Chase order", () => {
  assert.deepEqual(overview.families.map((family) => family.key), ["raw", "topChase"]);
  assert.deepEqual(overview.families.map((family) => family.label), ["Raw Card Market", "Top 10 Chase Market"]);
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

test("help text names the basket honestly and never as market capitalization", () => {
  const copy = Object.values(MARKET_OVERVIEW_HELP).join(" ").toLowerCase();
  assert.ok(copy.includes("this is not market capitalization"));
  assert.ok(copy.includes("base value of 100"));
  assert.doesNotMatch(copy, /market cap\b/);
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
