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
  SHARED_COMPARISON_WINDOW_LABEL,
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
  getSharedComparisonChange,
  getTrackedValueChange,
  isMarketWindowAvailable,
  projectMarketPageOverview,
  resolveDefaultMarketWindow,
  resolveMarketOverview,
} from "./marketOverviewPresentation.mjs";

test("the /Market projection removes Top Chase without mutating canonical data", () => {
  const canonical = { families: [{ key: "raw" }, { key: "topChase" }, { key: "sealedMarket" }], coverage: { chaseCardCount: 100 } };
  const projected = projectMarketPageOverview(canonical);
  assert.deepEqual(projected.families.map((family) => family.key), ["raw", "sealedMarket"]);
  assert.deepEqual(canonical.families.map((family) => family.key), ["raw", "topChase", "sealedMarket"]);
  assert.equal(projected.coverage.chaseCardCount, 100);
});

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
    comparisonWindows: {
      "1D": { targetStartDate: "2024-01-03", displayStartDate: "2024-01-03", displayEndDate: "2024-01-04", available: true },
      "7D": { targetStartDate: "2023-12-28", displayStartDate: "2024-01-02", displayEndDate: "2024-01-04", available: true },
      "30D": { targetStartDate: "2023-12-05", displayStartDate: "2024-01-02", displayEndDate: "2024-01-04", available: true },
      "3M": { targetStartDate: "2023-10-07", displayStartDate: "2023-10-07", displayEndDate: "2024-01-04", available: false },
      "6M": { targetStartDate: "2023-07-09", displayStartDate: "2023-07-09", displayEndDate: "2024-01-04", available: false },
      "1Y": { targetStartDate: "2023-01-05", displayStartDate: "2023-01-05", displayEndDate: "2024-01-04", available: false },
      SinceTracking: { targetStartDate: "2024-01-02", displayStartDate: "2024-01-02", displayEndDate: "2024-01-04", available: true },
    },
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
      // THIS MARKET'S OWN HISTORY. Its SinceTracking reconciles with the
      // published index of 102.25, which is what the All button must show.
      familyChanges: {
        "1D": change(2.7638, "2024-01-03", "2024-01-04"),
        "7D": change(2.25, "2024-01-01", "2024-01-04"),
        "30D": change(2.25, "2024-01-01", "2024-01-04"),
        "3M": missing("2024-01-04", "2023-10-07"),
        "6M": missing("2024-01-04", "2023-07-09"),
        "1Y": missing("2024-01-04", "2023-01-06"),
        SinceTracking: change(2.25, "2024-01-01", "2024-01-04"),
      },
      // THE SHARED COMPARABLE DOMAIN, which begins a day later because one
      // compared market does. Deliberately a DIFFERENT number under the same
      // key: it is preserved, but no timeframe button may read it.
      changes: {
        "1D": change(2.7638, "2024-01-03", "2024-01-04"),
        "7D": change(1.2376, "2024-01-02", "2024-01-04"),
        "30D": change(1.2376, "2024-01-02", "2024-01-04"),
        "3M": missing("2024-01-04", "2023-10-07"),
        "6M": missing("2024-01-04", "2023-07-09"),
        "1Y": missing("2024-01-04", "2023-01-06"),
        SinceTracking: change(1.2376, "2024-01-02", "2024-01-04"),
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
      familyChanges: {
        "1D": change(-0.5154, "2024-01-03", "2024-01-04"),
        "7D": change(-3.5, "2024-01-01", "2024-01-04"),
        "30D": change(-3.5, "2024-01-01", "2024-01-04"),
        "3M": missing("2024-01-04", "2023-10-07"),
        "6M": missing("2024-01-04", "2023-07-09"),
        "1Y": missing("2024-01-04", "2023-01-06"),
        SinceTracking: change(-3.5, "2024-01-01", "2024-01-04"),
      },
      changes: {
        "1D": change(-0.5154, "2024-01-03", "2024-01-04"),
        "7D": change(-1.5306, "2024-01-02", "2024-01-04"),
        "30D": change(-1.5306, "2024-01-02", "2024-01-04"),
        "3M": missing("2024-01-04", "2023-10-07"),
        "6M": missing("2024-01-04", "2023-07-09"),
        "1Y": missing("2024-01-04", "2023-01-06"),
        SinceTracking: change(-1.5306, "2024-01-02", "2024-01-04"),
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
  familyChanges: {
    "1D": change(1.4423, "2024-01-03", "2024-01-04"),
    "7D": change(5.5, "2024-01-01", "2024-01-04"),
    "30D": change(5.5, "2024-01-01", "2024-01-04"),
    "3M": missing("2024-01-04", "2023-10-07"),
    "6M": missing("2024-01-04", "2023-07-09"),
    "1Y": missing("2024-01-04", "2023-01-06"),
    SinceTracking: change(5.5, "2024-01-01", "2024-01-04"),
  },
  changes: {
    "1D": change(1.4423, "2024-01-03", "2024-01-04"),
    "7D": change(5.5, "2024-01-02", "2024-01-04"),
    "30D": change(5.5, "2024-01-02", "2024-01-04"),
    "3M": missing("2024-01-04", "2023-10-07"),
    "6M": missing("2024-01-04", "2023-07-09"),
    "1Y": missing("2024-01-04", "2023-01-06"),
    SinceTracking: change(5.5, "2024-01-02", "2024-01-04"),
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

test("a window's span excludes stale points and preserves missing calendar dates", () => {
  const payload = structuredClone(snapshotWithSealed);
  payload.marketOverview.marketDate = "2026-08-24";
  for (const familyKey of ["raw", "topChase", "sealedMarket"]) {
    payload.marketOverview[familyKey].trend = [["2026-07-16", 99], ["2026-07-26", 100], ["2026-07-29", 101], ["2026-08-24", 102]];
    payload.marketOverview[familyKey].familyChanges["30D"] = {
      available: true, percent: 2, startDate: "2026-07-26", endDate: "2026-08-24",
      targetStartDate: "2026-07-25", coverage: "full",
    };
  }
  const model = buildMarketPerformanceSeries(resolveMarketOverview(payload), "30D");
  assert.equal(model.startDate, "2026-07-26");
  assert.equal(model.endDate, "2026-08-24");
  assert.equal(model.dates.length, 30);
  assert.equal(model.dates.includes("2026-07-16"), false);
  const sealed = model.series.find((entry) => entry.key === "sealedMarket");
  assert.equal(sealed.values[0], 100);
  assert.equal(sealed.values[3], 101);
});

test("one unavailable family does not disable a named comparison window", () => {
  const payload = structuredClone(snapshotWithSealed);
  payload.marketOverview.sealedMarket.familyChanges["1D"] = missing("2024-01-04", "2024-01-03");
  const resolved = resolveMarketOverview(payload);
  assert.equal(isMarketWindowAvailable(resolved, "1D"), true);
  const model = buildMarketPerformanceSeries(resolved, "1D");
  assert.equal(model.startDate, "2024-01-03");
  assert.deepEqual(model.series.find((entry) => entry.key === "sealedMarket").values, [null, null]);
  assert.deepEqual(model.series.filter((entry) => entry.values.some((value) => value !== null)).map((entry) => entry.key), ["raw", "topChase"]);
});

test("Sealed 1D uses comparison-only carried provenance without mutating canonical trend", () => {
  const payload = structuredClone(snapshotWithSealed);
  payload.marketOverview.marketDate = "2026-08-24";
  payload.marketOverview.comparisonWindows["1D"] = {
    targetStartDate: "2026-08-23", displayStartDate: "2026-08-23",
    displayEndDate: "2026-08-24", available: true, coverage: "full",
  };
  payload.marketOverview.sealedMarket.trend = [
    ["2026-08-22", 106.21882536871614], ["2026-08-24", 106.17849310930887],
  ];
  payload.marketOverview.sealedMarket.oneDayComparison = {
    comparisonTrend: [
      { date: "2026-08-23", value: 106.21882536871614, isObserved: false, isCarriedForward: true, sourceDate: "2026-08-22" },
      { date: "2026-08-24", value: 106.17849310930887, isObserved: true, isCarriedForward: false, sourceDate: "2026-08-24" },
    ],
  };
  payload.marketOverview.sealedMarket.familyChanges["1D"] = {
    available: true, percent: -0.03797091454105228,
    startDate: "2026-08-23", endDate: "2026-08-24",
    targetStartDate: "2026-08-23", coverage: "carried_previous_close",
    isCarriedForwardBaseline: true, baselineSourceDate: "2026-08-22",
  };
  for (const key of ["raw", "topChase"]) {
    payload.marketOverview[key].trend = [["2026-08-23", 100], ["2026-08-24", 101]];
    payload.marketOverview[key].familyChanges["1D"] = change(1, "2026-08-23", "2026-08-24");
  }
  const resolved = resolveMarketOverview(payload);
  const sealed = resolved.families.find((family) => family.key === "sealedMarket");
  const model = buildMarketPerformanceSeries(resolved, "1D");
  assert.deepEqual(model.dates, ["2026-08-23", "2026-08-24"]);
  assert.deepEqual(model.series.map((entry) => entry.key), ["raw", "topChase", "sealedMarket"]);
  assert.deepEqual(model.series.find((entry) => entry.key === "sealedMarket").values, [106.21882536871614, 106.17849310930887]);
  assert.equal(model.series.find((entry) => entry.key === "sealedMarket").pointMeta[0].sourceDate, "2026-08-22");
  assert.equal(model.series.find((entry) => entry.key === "sealedMarket").pointMeta[0].isCarriedForward, true);
  assert.deepEqual(sealed.trend.map((point) => point.date), ["2026-08-22", "2026-08-24"]);
  assert.equal(getMarketChange(sealed, "1D").coverage, "carried_previous_close");
});

test("partial 6M and 1Y fall back to each series' own first observation and stay selectable", () => {
  const payload = structuredClone(snapshotWithSealed);
  for (const key of ["6M", "1Y"]) {
    payload.marketOverview.comparisonWindows[key] = {
      targetStartDate: key === "6M" ? "2023-07-09" : "2023-01-05",
      displayStartDate: "2024-01-01",
      displayEndDate: "2024-01-04",
      available: true,
      coverage: "partial",
      isSinceFirstAvailable: true,
    };
    for (const familyKey of ["raw", "topChase", "sealedMarket"]) {
      payload.marketOverview[familyKey].familyChanges[key] = {
        ...payload.marketOverview[familyKey].familyChanges.SinceTracking,
        coverage: "partial",
        isSinceFirstAvailable: true,
        targetStartDate: payload.marketOverview.comparisonWindows[key].targetStartDate,
      };
    }
  }
  const resolved = resolveMarketOverview(payload);
  const options = buildMarketWindowOptions(resolved);
  for (const key of ["6M", "1Y"]) {
    const option = options.find((entry) => entry.key === key);
    assert.equal(option.available, true);
    assert.equal(option.isSinceFirstAvailable, true);
    assert.match(option.ariaLabel, /shown since first available history/);
    const model = buildMarketPerformanceSeries(resolved, key);
    assert.equal(model.startDate, buildMarketPerformanceSeries(resolved, "All").startDate);
    for (const family of resolved.families) {
      assert.equal(getMarketChange(family, key).percent, getMarketChange(family, "All").percent);
    }
  }
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
  // Constituents, not "sets": the same index copy now also describes Sealed,
  // whose constituents are products. The claim being guarded is unchanged —
  // entry is neutralized, and later movement still counts.
  assert.match(MARKET_OVERVIEW_HELP.index, /after one enters, its later price movement affects the index/i);
  // The index level must be explained against its OWN base, and must not be
  // read as a claim about every constituent.
  assert.match(MARKET_OVERVIEW_HELP.index, /above its own index base/i);
  assert.match(MARKET_OVERVIEW_HELP.index, /does not mean every card or product in it rose/i);
  // "Since Tracking" and the shared "All" window must be described as
  // different spans, never as the same statement.
  assert.match(MARKET_OVERVIEW_HELP.sinceTracking, /this market's own tracking start/i);
  assert.match(MARKET_OVERVIEW_HELP.sharedComparison, /common comparable start/i);
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
  assert.equal(getPricePerformanceChange(raw, "All"), raw.familyChanges.SinceTracking);
  // ...and it is this market's OWN history, which reconciles with its
  // published index of 102.25 — not the shared comparable span's +1.24%.
  assert.equal(getSharedComparisonChange(raw, "All").percent, 1.2376);
  assert.notEqual(getPricePerformanceChange(raw, "All").percent, getSharedComparisonChange(raw, "All").percent);
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
      raw: { basketValue: 8123.45, indexValue: 102.25, historyStartDate: "2024-01-01", trend: RAW_TREND, familyChanges: { SinceTracking: change(2.25, "2024-01-01", "2024-01-04") } },
      topChase: { basketValue: 4011.1, indexValue: 96.5, historyStartDate: "2024-01-01", trend: CHASE_TREND, familyChanges: { SinceTracking: change(-3.5, "2024-01-01", "2024-01-04") } },
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
  assert.equal(model.series[0].change, overview.families[0].familyChanges.SinceTracking);
  assert.notEqual(model.series[0].change, overview.families[0].basketChanges.SinceTracking);
});

test("All reconciles with the published Market Index for every family", () => {
  // THE AUDIT ASSERTION, made here and nowhere in production code: a
  // continuous base-100 series whose index reads X must report All as
  // approximately (X / 100 - 1) * 100. This is what makes "Market Index
  // 105.87" and "ALL +3.76%" impossible to ship together again.
  for (const family of sealedOverview.families) {
    const all = getPricePerformanceChange(family, "All");
    assert.equal(all.available, true);
    assert.ok(Math.abs(all.percent - (family.indexValue / 100 - 1) * 100) < 1e-9,
      `${family.key}: All ${all.percent} must reconcile with index ${family.indexValue}`);
  }
});

test("the shared comparable series is preserved but never named All or Since Tracking", () => {
  const raw = overview.families[0];
  assert.equal(getSharedComparisonChange(raw, "All"), raw.changes.SinceTracking);
  assert.equal(getSharedComparisonChange(raw, "7D").startDate, "2024-01-02");
  assert.equal(SHARED_COMPARISON_WINDOW_LABEL, "Since Comparable Start");
  // No timeframe button routes to it.
  assert.notEqual(getPricePerformanceChange(raw, "All"), getSharedComparisonChange(raw, "All"));
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

test("a parent market's published constituent roster survives normalization", () => {
  // Total Sealed is the only parent that publishes one, and it is the only
  // surface showing the `otherSealed` residual products. normalizeFamily builds
  // an explicit allow-list, so a field it forgets is silently dropped between a
  // correct API response and the panel — which is exactly what happened here.
  const overview = resolveMarketOverview({
    marketOverview: {
      marketDate: "2026-08-25",
      sealedMarket: {
        basketValue: 22860.88,
        indexValue: 105.87,
        historyStartDate: "2026-04-07",
        changes: { "7D": { percent: -0.49, available: true } },
        trend: [["2026-08-25", 105.87]],
        currentConstituents: {
          contractVersion: "pokemon-prepared-constituent-summary-v1",
          asOf: "2026-08-25",
          totalCount: 139,
          limit: 250,
          isComplete: true,
          idField: "sealedProductId",
          topConstituents: [{ sealedProductId: "p-1", productName: "A", marketPrice: 10 }],
        },
      },
      raw: {
        basketValue: 39344.72,
        indexValue: 101.04,
        historyStartDate: "2026-04-23",
        changes: { "7D": { percent: -0.3, available: true } },
        trend: [["2026-08-25", 101.04]],
      },
    },
  });

  const sealed = overview.families.find((family) => family.key === "sealedMarket");
  assert.equal(sealed.currentConstituents.totalCount, 139);
  assert.equal(sealed.currentConstituents.isComplete, true);

  // A parent that publishes nothing stays null rather than inheriting anything.
  const raw = overview.families.find((family) => family.key === "raw");
  assert.equal(raw.currentConstituents, null);
});
