// Pokémon Market Performance: one dual-series normalized-index chart.
//
// Guards the two ways this section could lie: charting basket dollars instead
// of index values, and offering a timeframe the snapshot cannot support.

import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer from "react-test-renderer";

import PokemonMarketPerformance from "./PokemonMarketPerformance.jsx";
import { resolveMarketOverview } from "@/lib/explore/marketOverviewPresentation.mjs";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const change = (percent, startDate) => ({ available: true, percent, startDate, endDate: "2024-01-05", coverage: "full" });
const missing = () => ({ available: false, percent: null, startDate: null, endDate: "2024-01-05", coverage: "unavailable" });

const RAW_TREND = [["2024-01-01", 100], ["2024-01-02", 101], ["2024-01-03", 99.5], ["2024-01-04", 101.75], ["2024-01-05", 102.25]];
const CHASE_TREND = [["2024-01-01", 100], ["2024-01-02", 98], ["2024-01-03", 97], ["2024-01-04", 96.75], ["2024-01-05", 96.5]];

const SNAPSHOT = {
  marketOverview: {
    marketDate: "2024-01-05",
    coverage: { eligibleSetCount: 3, rawCardCount: 512, chaseCardCount: 30 },
    raw: {
      basketValue: 8123.45, indexValue: 102.25, historyStartDate: "2024-01-01", trend: RAW_TREND,
      changes: { "1D": change(0.49, "2024-01-04"), "7D": change(2.25, "2024-01-01"), "30D": change(2.25, "2024-01-01"), "3M": missing(), "6M": missing(), "1Y": missing(), SinceTracking: change(2.25, "2024-01-01") },
    },
    topChase: {
      basketValue: 4011.1, indexValue: 96.5, historyStartDate: "2024-01-01", trend: CHASE_TREND,
      changes: { "1D": change(-0.26, "2024-01-04"), "7D": change(-3.5, "2024-01-01"), "30D": change(-3.5, "2024-01-01"), "3M": missing(), "6M": missing(), "1Y": missing(), SinceTracking: change(-3.5, "2024-01-01") },
    },
  },
};

const overview = resolveMarketOverview(SNAPSHOT);

function render(value = overview) {
  let renderer;
  TestRenderer.act(() => {
    renderer = TestRenderer.create(React.createElement(PokemonMarketPerformance, { overview: value }));
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

test("the section carries the locked heading and its accessible sub-label", () => {
  const renderer = render();
  assert.equal(textOf(renderer.root.findAll((node) => node.props?.id === "market-performance-heading")[0]), "Pokémon Market Performance");
  assert.equal(
    textOf(renderer.root.findAll((node) => node.props?.id === "market-performance-description")[0]),
    "Normalized performance of the Raw Card Market and Top 10 Chase Market."
  );
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

test("the plotted values are normalized index values, never basket dollars", () => {
  const renderer = render();
  // The default window is 30D, which the fixture covers from the first day.
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
  assert.deepEqual(stillSelected.map((node) => node.props["data-market-window-value"]), ["30D"]);
  // The legend still reports the 30D backend percentages, unchanged.
  const legend = textOf(renderer.root.findAll((node) => node.props?.["data-market-performance-legend"] !== undefined)[0]);
  assert.match(legend, /30D: up 2\.25 percent/);
  assert.match(legend, /30D: down 3\.50 percent/);
  assert.doesNotMatch(legend, /6M/);
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
    let renderer;
    TestRenderer.act(() => { renderer = TestRenderer.create(React.createElement(PokemonMarketPerformance, { overview: value })); });
    assert.equal(renderer.toJSON(), null);
  }
});
