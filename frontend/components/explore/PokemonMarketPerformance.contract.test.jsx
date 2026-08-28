// Pokémon Market Performance: one dual-series normalized-index chart.
//
// Guards the two ways this section could lie: charting basket dollars instead
// of index values, and offering a timeframe the snapshot cannot support.

import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer from "react-test-renderer";

// Rendered through the analysis surface, which owns the ONE timeframe state
// the chart and the Market Overview period column share. Testing the pane in
// isolation would test a window selection that cannot exist in the product.
import PokemonMarketAnalysis from "./PokemonMarketAnalysis.jsx";
import { filterMarketPerformanceModel } from "./PokemonMarketPerformance.jsx";
import { resolveMarketOverview } from "@/lib/explore/marketOverviewPresentation.mjs";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const change = (percent, startDate) => ({ available: true, percent, startDate, endDate: "2024-01-05", coverage: "full" });
const missing = () => ({ available: false, percent: null, startDate: null, endDate: "2024-01-05", coverage: "unavailable" });

const RAW_TREND = [["2024-01-01", 100], ["2024-01-02", 101], ["2024-01-03", 99.5], ["2024-01-04", 101.75], ["2024-01-05", 102.25]];
const CHASE_TREND = [["2024-01-01", 100], ["2024-01-02", 98], ["2024-01-03", 97], ["2024-01-04", 96.75], ["2024-01-05", 96.5]];

const SNAPSHOT = {
  marketOverview: {
    marketDate: "2024-01-05",
    comparisonWindows: {
      "1D": { targetStartDate: "2024-01-04", displayStartDate: "2024-01-04", displayEndDate: "2024-01-05", available: true },
      "7D": { targetStartDate: "2024-01-01", displayStartDate: "2024-01-01", displayEndDate: "2024-01-05", available: true },
      "30D": { targetStartDate: "2024-01-01", displayStartDate: "2024-01-01", displayEndDate: "2024-01-05", available: true },
      "3M": { targetStartDate: "2023-10-08", displayStartDate: "2023-10-08", displayEndDate: "2024-01-05", available: false },
      "6M": { targetStartDate: "2023-07-10", displayStartDate: "2023-07-10", displayEndDate: "2024-01-05", available: false },
      "1Y": { targetStartDate: "2023-01-06", displayStartDate: "2023-01-06", displayEndDate: "2024-01-05", available: false },
      SinceTracking: { targetStartDate: "2024-01-01", displayStartDate: "2024-01-01", displayEndDate: "2024-01-05", available: true },
    },
    coverage: { eligibleSetCount: 3, rawCardCount: 512, chaseCardCount: 30 },
    raw: {
      basketValue: 8123.45, indexValue: 102.25, historyStartDate: "2024-01-01", trend: RAW_TREND,
      // Tracked Value moved very differently. If any of it leaks into this
      // chart or its legend, the assertions below fail loudly.
      basketChanges: { "1D": change(11.11, "2024-01-04"), "7D": change(22.22, "2024-01-01"), "30D": change(33.33, "2024-01-01"), "3M": missing(), "6M": missing(), "1Y": missing(), SinceTracking: change(44.44, "2024-01-01") },
      changes: { "1D": change(0.49, "2024-01-04"), "7D": change(2.25, "2024-01-01"), "30D": change(2.25, "2024-01-01"), "3M": missing(), "6M": missing(), "1Y": missing(), SinceTracking: change(2.25, "2024-01-01") },
      familyChanges: { "1D": change(0.49, "2024-01-04"), "7D": change(2.25, "2024-01-01"), "30D": change(2.25, "2024-01-01"), "3M": missing(), "6M": missing(), "1Y": missing(), SinceTracking: change(6.18, "2024-01-01") },
    },
    topChase: {
      basketValue: 4011.1, indexValue: 96.5, historyStartDate: "2024-01-01", trend: CHASE_TREND,
      basketChanges: { "1D": change(55.55, "2024-01-04"), "7D": change(66.66, "2024-01-01"), "30D": change(77.77, "2024-01-01"), "3M": missing(), "6M": missing(), "1Y": missing(), SinceTracking: change(88.88, "2024-01-01") },
      changes: { "1D": change(-0.26, "2024-01-04"), "7D": change(-3.5, "2024-01-01"), "30D": change(-3.5, "2024-01-01"), "3M": missing(), "6M": missing(), "1Y": missing(), SinceTracking: change(-3.5, "2024-01-01") },
      familyChanges: { "1D": change(-0.26, "2024-01-04"), "7D": change(-3.5, "2024-01-01"), "30D": change(-3.5, "2024-01-01"), "3M": missing(), "6M": missing(), "1Y": missing(), SinceTracking: change(-8.4, "2024-01-01") },
    },
  },
};

const overview = resolveMarketOverview(SNAPSHOT);

function render(value = overview) {
  let renderer;
  TestRenderer.act(() => {
    renderer = TestRenderer.create(React.createElement(PokemonMarketAnalysis, { overview: value }));
  });
  return renderer;
}

function textOf(node) {
  if (node === null || node === undefined || node === false) return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  return (node.children || []).map(textOf).filter(Boolean).join(" ");
}

const windowButtons = (renderer) => renderer.root.findAll((node) => node.props?.["data-market-window-value"] !== undefined);
const seriesLines = (renderer) => renderer.root.findAll((node) => node.props?.["data-market-performance-series"] !== undefined);
const tableToggle = (renderer, key) => renderer.root.find((node) => node.props?.["data-market-overview-toggle"] === key);
const legendToggle = (renderer, key) => renderer.root.find((node) => node.props?.["data-market-performance-toggle"] === key);

test("the section carries the locked heading and its accessible sub-label", () => {
  const renderer = render();
  const cta = renderer.root.find((node) => node.props?.["data-market-explorer-cta"] !== undefined);
  assert.equal(cta.props.href, "/Market/Explorer");
  assert.match(textOf(cta), /Open Market Explorer/);
  assert.match(String(cta.props.className), /45,212,191/);
  assert.equal(textOf(renderer.root.findAll((node) => node.props?.id === "market-performance-heading")[0]), "Pokémon Market Performance");
  const description = textOf(renderer.root.findAll((node) => node.props?.id === "market-performance-description")[0]);
  // Shortened so it cannot collide with the pane's controls, with its factual
  // claim intact: chain-linked, and immune to new-set additions.
  assert.match(description, /Chain-linked price performance\./);
  assert.match(description, /New-set additions do not create artificial jumps\./);
  // Which markets those are is carried by the legend and the Overview rows.
  assert.ok(renderer.root.findAll((node) => node.props?.["data-market-performance-legend-item"] === "raw").length > 0);
  assert.ok(renderer.root.findAll((node) => node.props?.["data-market-performance-legend-item"] === "topChase").length > 0);
});

test("one chart draws both series with stable identity colors", () => {
  const renderer = render();
  const lines = seriesLines(renderer);
  assert.deepEqual(lines.map((node) => node.props["data-market-performance-series"]), ["raw", "topChase"]);
  assert.notEqual(lines[0].props.stroke, lines[1].props.stroke);
  // Identity, never gain/loss: neither line is painted with a semantic tone
  // even though raw is up over the window and chase is down.
  for (const line of lines) {
    assert.doesNotMatch(String(line.props.stroke), /248,\s*113|45,\s*212/);
  }
  assert.equal(renderer.root.findAll((node) => node.props?.["data-market-performance-chart"] !== undefined).length, 1);
});

test("mobile hides duplicate explanation and legend while retaining info, controls and a compact real chart", () => {
  const renderer = render();
  const description = renderer.root.find((node) => node.props?.id === "market-performance-description");
  assert.match(String(description.props.className), /hidden[\s\S]*desk:block/);
  const legend = renderer.root.find((node) => node.props?.["data-market-performance-legend"] !== undefined);
  assert.match(String(legend.props.className), /hidden[\s\S]*desk:flex/);
  assert.ok(renderer.root.findAll((node) => typeof node.type === "function" && /Chain-linked price performance/.test(String(node.props?.text || ""))).length >= 1);
  const chart = renderer.root.find((node) => node.props?.["data-market-performance-chart"] !== undefined);
  assert.match(String(chart.props.className), /h-40 desk:h-\[13\.5rem\]/);
});

test("table and legend share one visibility state and can restore either family", () => {
  const renderer = render();
  assert.equal(tableToggle(renderer, "raw").props["aria-pressed"], true);
  assert.equal(legendToggle(renderer, "raw").props["aria-pressed"], true);
  assert.equal(legendToggle(renderer, "topChase").props["aria-pressed"], true);

  TestRenderer.act(() => { tableToggle(renderer, "raw").props.onClick(); });
  assert.equal(tableToggle(renderer, "raw").props["aria-pressed"], false);
  assert.equal(legendToggle(renderer, "raw").props["aria-pressed"], false);
  assert.deepEqual(seriesLines(renderer).map((node) => node.props["data-market-performance-series"]), ["topChase"]);

  TestRenderer.act(() => { legendToggle(renderer, "raw").props.onClick(); });
  assert.equal(tableToggle(renderer, "raw").props["aria-pressed"], true);
  assert.deepEqual(seriesLines(renderer).map((node) => node.props["data-market-performance-series"]), ["raw", "topChase"]);
});

test("hidden series are excluded from geometry, markers, readings and domain", () => {
  const renderer = render();
  const fullChart = renderer.root.find((node) => node.props?.["data-market-performance-chart"] !== undefined);
  const fullDomainMax = fullChart.props["data-market-performance-domain-max"];
  TestRenderer.act(() => { tableToggle(renderer, "raw").props.onClick(); });
  const chart = renderer.root.find((node) => node.props?.["data-market-performance-chart"] !== undefined);
  assert.ok(chart.props["data-market-performance-domain-max"] < fullDomainMax, "hidden Raw values no longer influence the Y domain");
  assert.ok(chart.props["data-market-performance-domain-max"] >= 100);
  assert.ok(chart.props["data-market-performance-domain-min"] < 96.5);
  assert.deepEqual(renderer.root.findAll((node) => node.props?.["data-market-performance-area"] !== undefined).map((node) => node.props["data-market-performance-area"]), ["topChase"]);

  TestRenderer.act(() => { chart.props.onFocus({ currentTarget: { getBoundingClientRect: () => ({ left: 0, top: 0, width: 400, height: 200 }) } }); });
  const selectedChart = renderer.root.find((node) => node.props?.["data-market-performance-chart"] !== undefined);
  assert.doesNotMatch(String(selectedChart.props["aria-label"]), /Raw Card Market/);
  assert.match(String(selectedChart.props["aria-label"]), /Top 10 Chase Market/);
  assert.deepEqual(renderer.root.findAll((node) => node.props?.["data-market-performance-marker"] !== undefined).map((node) => node.props["data-market-performance-marker"]), ["topChase"]);
});

test("all families may be hidden without collapsing or claiming history is missing", () => {
  const renderer = render();
  TestRenderer.act(() => { legendToggle(renderer, "raw").props.onClick(); });
  TestRenderer.act(() => { legendToggle(renderer, "topChase").props.onClick(); });
  const empty = renderer.root.find((node) => node.props?.["data-market-performance-visibility-empty"] !== undefined);
  assert.match(textOf(empty), /Select a market to display\./);
  assert.match(String(empty.props.className), /h-40 desk:h-\[13\.5rem\]/);
  assert.equal(seriesLines(renderer).length, 0);
  assert.equal(tableToggle(renderer, "raw").props["aria-pressed"], false);
  assert.equal(tableToggle(renderer, "topChase").props["aria-pressed"], false);
});

test("filtering uses stable keys and scales beyond two series", () => {
  const model = { dates: ["a", "b"], series: ["raw", "topChase", "sealed", "graded"].map((key) => ({ key, values: [1, 2] })) };
  const filtered = filterMarketPerformanceModel(model, new Set(["topChase", "graded"]));
  assert.deepEqual(filtered.series.map((series) => series.key), ["topChase", "graded"]);
  assert.deepEqual(model.series.map((series) => series.key), ["raw", "topChase", "sealed", "graded"], "source model remains unchanged");
});

test("the plotted values are normalized index values, never basket dollars", () => {
  const renderer = render();
  // The default window is 7D, which the fixture covers from the first day.
  const chartText = seriesLines(renderer).map((node) => String(node.props.points)).join(" ");
  assert.ok(chartText.length > 0);
  const legend = textOf(renderer.root.findAll((node) => node.props?.["data-market-performance-legend"] !== undefined)[0]);
  assert.doesNotMatch(legend, /\$8,123\.45|\$4,011\.10/);
  assert.match(legend, /Raw Card Market/);
  assert.match(legend, /Top 10 Chase Market/);
  assert.match(legend, /\+2\.25%/);
  assert.match(legend, /−3\.50%/);
});

test("the timeframe selector offers 1D through All and disables what history cannot support", () => {
  const renderer = render();
  const buttons = windowButtons(renderer);
  assert.deepEqual(buttons.map((node) => node.props["data-market-window-value"]), ["1D", "7D", "30D", "3M", "6M", "1Y", "All"]);
  const byKey = Object.fromEntries(buttons.map((node) => [node.props["data-market-window-value"], node.props]));
  for (const key of ["3M", "6M", "1Y"]) {
    assert.equal(byKey[key].disabled, true, `${key} must be disabled`);
    assert.equal(byKey[key]["aria-label"], `${key} — not enough history`);
  }
  for (const key of ["1D", "7D", "30D", "All"]) {
    assert.equal(byKey[key].disabled, false, `${key} must be selectable`);
  }
});

test("an unavailable timeframe cannot be selected, and no partial percentage appears", () => {
  const renderer = render();
  const sixMonth = windowButtons(renderer).find((node) => node.props["data-market-window-value"] === "6M");
  TestRenderer.act(() => { sixMonth.props.onClick(); });

  // Still on the default window — nothing fabricated, nothing substituted.
  const stillSelected = windowButtons(renderer).filter((node) => node.props["aria-checked"] === true);
  assert.deepEqual(stillSelected.map((node) => node.props["data-market-window-value"]), ["7D"]);
  // The legend still reports the 7D backend percentages, unchanged.
  const legend = textOf(renderer.root.findAll((node) => node.props?.["data-market-performance-legend"] !== undefined)[0]);
  assert.match(legend, /7D: up 2\.25 percent/);
  assert.match(legend, /7D: down 3\.50 percent/);
  assert.doesNotMatch(legend, /6M/);
});

test("partial 6M and 1Y are selectable and visibly say since first available", () => {
  const payload = structuredClone(SNAPSHOT);
  for (const key of ["6M", "1Y"]) {
    payload.marketOverview.comparisonWindows[key] = {
      targetStartDate: key === "6M" ? "2023-07-10" : "2023-01-06",
      displayStartDate: "2024-01-01",
      displayEndDate: "2024-01-05",
      available: true,
      coverage: "partial",
      isSinceFirstAvailable: true,
    };
    for (const familyKey of ["raw", "topChase"]) {
      payload.marketOverview[familyKey].familyChanges[key] = {
        ...payload.marketOverview[familyKey].familyChanges.SinceTracking,
        coverage: "partial",
        isSinceFirstAvailable: true,
      };
    }
  }
  const renderer = render(resolveMarketOverview(payload));
  for (const key of ["6M", "1Y"]) {
    const button = windowButtons(renderer).find((node) => node.props["data-market-window-value"] === key);
    assert.equal(button.props.disabled, false);
    assert.match(button.props["aria-label"], /shown since first available history/);
    TestRenderer.act(() => { button.props.onClick(); });
    assert.match(textOf(renderer.root.find((node) => node.props?.["data-market-performance-coverage-note"] !== undefined)), /Since first available/);
    assert.match(textOf(renderer.root.find((node) => node.props?.["data-market-overview-period-heading"] === key)), new RegExp(`${key}.*Since first available`));
    assert.deepEqual(seriesLines(renderer).map((node) => node.props["data-market-performance-series"]), ["raw", "topChase"]);
  }
});

test("selecting a window clips the chart to the backend window's dates", () => {
  const renderer = render();
  const oneDay = windowButtons(renderer).find((node) => node.props["data-market-window-value"] === "1D");
  TestRenderer.act(() => { oneDay.props.onClick(); });

  const dates = renderer.root.findAll((node) => node.props?.["data-market-performance-dates"] !== undefined)[0];
  // 1D's backend change object spans 2024-01-04 → 2024-01-05.
  assert.match(textOf(dates), /Jan 4/);
  assert.match(textOf(dates), /Jan 5/);
  assert.doesNotMatch(textOf(dates), /Jan 1\b/);

  const legend = textOf(renderer.root.findAll((node) => node.props?.["data-market-performance-legend"] !== undefined)[0]);
  assert.match(legend, /\+0\.49%/);
  assert.match(legend, /−0\.26%/);
});

test("the chart is keyboard reachable and announces the selected reading", () => {
  const renderer = render();
  const chart = renderer.root.findAll((node) => node.props?.["data-market-performance-chart"] !== undefined)[0];
  assert.equal(chart.props.tabIndex, 0);
  assert.equal(chart.props.role, "img");
  assert.match(String(chart.props["aria-label"]), /arrow keys/i);
  assert.equal(typeof chart.props.onKeyDown, "function");

  TestRenderer.act(() => { chart.props.onKeyDown({ key: "ArrowLeft", preventDefault() {}, currentTarget: { getBoundingClientRect: () => ({ left: 0, top: 0, width: 400, height: 200 }) } }); });
  const updated = renderer.root.findAll((node) => node.props?.["data-market-performance-chart"] !== undefined)[0];
  assert.match(String(updated.props["aria-label"]), /Raw Card Market index/);
  assert.match(String(updated.props["aria-label"]), /Top 10 Chase Market index/);
});

test("no overview means no performance section at all, rather than an empty chart", () => {
  for (const value of [null, undefined, { families: [] }]) {
    // Constructed directly: render()'s default parameter would substitute the
    // live fixture for `undefined` and quietly test the wrong case.
    let renderer;
    TestRenderer.act(() => { renderer = TestRenderer.create(React.createElement(PokemonMarketAnalysis, { overview: value })); });
    assert.equal(renderer.root.findAll((node) => node.props?.["data-market-performance-pane"] !== undefined).length, 0);
    assert.equal(windowButtons(renderer).length, 0, "no timeframe control without a market to chart");
    // The surface still says so, rather than rendering an empty analysis.
    assert.match(textOf(renderer.toJSON()), /Market Overview is temporarily unavailable\./);
  }
});

test("ONE timeframe drives both the chart and the Market Overview period column", () => {
  const renderer = render();
  const periodHeading = () => renderer.root.findAll((node) => node.props?.["data-market-overview-period-heading"] !== undefined)[0];
  const periodCells = () => renderer.root.findAll(
    (node) => node.type === "td" && node.props?.["data-market-overview-change"] !== undefined
  );

  // Default: 7D, in the table heading and in the chart's own selection. The
  // heading carries its own ⓘ, so match rather than compare exactly.
  assert.match(textOf(periodHeading()), /^7D/);
  assert.equal(periodHeading().props["data-market-overview-period-heading"], "7D");
  assert.deepEqual(periodCells().map((node) => node.props["data-market-overview-change"]), ["7D", "7D"]);
  assert.match(textOf(periodCells()[0]), /−?\+?2\.25%/);

  // Selecting 1D on the chart's selector moves the table column with it.
  const oneDay = windowButtons(renderer).find((node) => node.props["data-market-window-value"] === "1D");
  TestRenderer.act(() => { oneDay.props.onClick(); });
  assert.match(textOf(periodHeading()), /^1D/);
  assert.deepEqual(periodCells().map((node) => node.props["data-market-overview-change"]), ["1D", "1D"]);
  // The published 1D price performance, not the 1D tracked-value change.
  assert.match(textOf(periodCells()[0]), /0\.49%/);
  assert.doesNotMatch(textOf(periodCells()[0]), /11\.11/);

  // THE FIXED "SINCE TRACKING" COLUMN IS GONE. One dynamic period column is
  // the only movement cell, so a heading can never describe a different span
  // from the number beneath it.
  assert.equal(renderer.root.findAll((node) => node.props?.["data-market-overview-tracked-change"] !== undefined).length, 0);
});

test("All is the market's OWN tracking start, never the shared comparable span", () => {
  const renderer = render();
  const all = windowButtons(renderer).find((node) => node.props["data-market-window-value"] === "All");
  TestRenderer.act(() => { all.props.onClick(); });

  const periodCell = renderer.root.findAll((node) => node.type === "td" && node.props?.["data-market-overview-change"] !== undefined)[0];
  // The family series (+6.18%), NOT the shared comparable span (+2.25%). This
  // is the whole defect: the shared number sat under a button labelled "All"
  // while the index level beside it told a different story.
  assert.match(textOf(periodCell), /6\.18%/);
  assert.doesNotMatch(textOf(periodCell), /2\.25%/);
  // Never the tracked-value series either.
  assert.doesNotMatch(textOf(periodCell), /44\.44/);

  const legend = textOf(renderer.root.findAll((node) => node.props?.["data-market-performance-legend"] !== undefined)[0]);
  assert.match(legend, /\+6\.18%/);
  assert.match(legend, /−8\.40%/);
  assert.doesNotMatch(legend, /\+2\.25%|−3\.50%/);
});


test("the chart and its legend stay on the price-performance dimension only", () => {
  const renderer = render();
  const legend = textOf(renderer.root.findAll((node) => node.props?.["data-market-performance-legend"] !== undefined)[0]);
  // The default 7D window: price performance is +2.25% / -3.50%; the tracked
  // basket moved +22.22% / +66.66% over the same window and must not appear.
  assert.match(legend, /\+2\.25%/);
  assert.match(legend, /−3\.50%/);
  assert.doesNotMatch(legend, /22\.22|66\.66|44\.44|88\.88/);
  assert.match(legend, /Price Performance, 7D: up 2\.25 percent/);

  // The plotted geometry is built from the index trend. Every charted value
  // sits in index territory, nowhere near the basket dollars.
  const plotted = seriesLines(renderer)
    .flatMap((node) => String(node.props.points).split(" "))
    .map((pair) => Number(pair.split(",")[1]))
    .filter(Number.isFinite);
  assert.ok(plotted.length > 0);

  const chart = renderer.root.findAll((node) => node.props?.["data-market-performance-chart"] !== undefined)[0];
  assert.doesNotMatch(String(chart.props["aria-label"]), /\$|8,123|4,011/);
});

test("switching windows never switches dimension", () => {
  const renderer = render();
  for (const key of ["1D", "7D", "All"]) {
    const button = windowButtons(renderer).find((node) => node.props["data-market-window-value"] === key);
    TestRenderer.act(() => { button.props.onClick(); });
    const legend = textOf(renderer.root.findAll((node) => node.props?.["data-market-performance-legend"] !== undefined)[0]);
    assert.doesNotMatch(legend, /11\.11|22\.22|44\.44|55\.55|66\.66|88\.88/, `${key} legend leaked a tracked-value percentage`);
    assert.match(legend, /Price Performance/);
  }
});

test("pointer, touch and keyboard interaction survive the clarification pass", () => {
  const renderer = render();
  const chart = renderer.root.findAll((node) => node.props?.["data-market-performance-chart"] !== undefined)[0];
  for (const handler of ["onPointerDown", "onPointerMove", "onPointerUp", "onPointerCancel", "onPointerLeave", "onFocus", "onBlur", "onKeyDown"]) {
    assert.equal(typeof chart.props[handler], "function", `${handler} must remain wired`);
  }
  assert.equal(chart.props.tabIndex, 0);
  assert.match(String(chart.props.className), /touch-pan-y/);
  assert.match(String(chart.props.className), /focus-visible:ring/);
});
