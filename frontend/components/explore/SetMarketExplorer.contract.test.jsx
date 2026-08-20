// Set Market: one master-detail surface built for a 167+ set catalogue.
//
// Guards the four ways this surface could regress:
//   1. drawing a chart per row again (the reason the ladder did not scale);
//   2. losing the in-place selection and going back to page navigation;
//   3. ranking, filtering or sorting on numbers the frontend derived;
//   4. losing the keyboard/AT affordances a clickable row must keep.

import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer from "react-test-renderer";

import SetMarketExplorer from "./SetMarketExplorer.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const movement = (amount, percent) => ({
  amount,
  percent,
  startDate: "2024-01-01",
  endDate: "2024-01-08",
  coverage: "full",
});

const trend = [["2024-01-01", 100], ["2024-01-04", 96], ["2024-01-08", 94]];

const TARGETS = [
  {
    setId: "set-a", canonicalKey: "ascended-heroes", name: "Ascended Heroes", era: "Mega Evolution",
    logoUrl: "https://example.test/a.png", currentSetValue: 6000.55, trend,
    windows: { "1D": movement(-12.5, -0.2), "7D": movement(-800.1, -11.8), "30D": movement(-40, -0.7), lifetime: movement(120, 2.1) },
  },
  {
    setId: "set-b", canonicalKey: "prismatic-evolutions", name: "Prismatic Evolutions", era: "Scarlet & Violet",
    logoUrl: "https://example.test/b.png", currentSetValue: 5023.63, trend,
    windows: { "1D": movement(3.1, 0.1), "7D": movement(-201.4, -3.9), "30D": movement(11, 0.2), lifetime: movement(80, 1.6) },
  },
  {
    setId: "set-c", canonicalKey: "black-bolt", name: "Black Bolt", era: "Scarlet & Violet",
    logoUrl: "", currentSetValue: 3589.7, trend,
    windows: { "1D": movement(1.2, 0.03), "7D": movement(-73.2, -2.0), "30D": movement(5, 0.1), lifetime: movement(50, 1.4) },
  },
  // Unpriced targets are not sets the market can rank, and must not appear.
  { setId: "set-d", canonicalKey: "no-value", name: "Unpriced Set", era: "Sword & Shield", currentSetValue: null, trend: [], windows: {} },
];

function render(props = {}) {
  let renderer;
  TestRenderer.act(() => {
    renderer = TestRenderer.create(React.createElement(SetMarketExplorer, { targets: TARGETS, ...props }));
  });
  return renderer;
}

function textOf(node) {
  if (node === null || node === undefined || node === false) return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  return (node.children || []).map(textOf).filter(Boolean).join(" ");
}

const rows = (renderer) => renderer.root.findAll((node) => node.props?.["data-set-market-row"] !== undefined);
const detail = (renderer) => renderer.root.findAll((node) => node.props?.["data-set-market-detail"] !== undefined)[0];
const detailName = (renderer) => textOf(renderer.root.findAll((node) => node.props?.["data-set-market-detail-name"] !== undefined)[0]);
const detailValue = (renderer) => textOf(renderer.root.findAll((node) => node.props?.["data-set-market-detail-value"] !== undefined)[0]);
const charts = (renderer) => renderer.root.findAll((node) => node.props?.["data-market-sparkline"] !== undefined || node.props?.["aria-label"]?.toString().includes("Set Value trend"));

test("the list renders every priced set, ranked by published Set Value", () => {
  const renderer = render();
  const labels = rows(renderer).map((node) => node.props["data-set-market-row"]);
  assert.deepEqual(labels, ["set-a", "set-b", "set-c"], "unpriced targets are omitted, not shown as zero");
});

test("rank is market-wide and comes from the published Set Value, not from the filter", () => {
  const renderer = render();
  const first = textOf(rows(renderer)[0]);
  assert.match(first, /#1/);
  assert.match(first, /Ascended Heroes/);
  assert.match(first, /Mega Evolution/);
});

test("exactly ONE chart is mounted, for the selected set — never one per row", () => {
  const renderer = render();
  assert.equal(charts(renderer).length, 1, "a 167-set catalogue must not mount 167 charts");
});

test("the #1 set is selected by default and its analysis is populated", () => {
  const renderer = render();
  assert.ok(detail(renderer), "the analysis pane renders alongside the list");
  assert.match(detailName(renderer), /Ascended Heroes/);
  assert.match(detailValue(renderer), /\$6,000\.55/);
});

test("selecting another row updates the analysis pane in place", () => {
  const renderer = render();
  const blackBolt = rows(renderer).find((node) => node.props["data-set-market-row"] === "set-c");
  TestRenderer.act(() => { blackBolt.props.onClick(); });

  assert.match(detailName(renderer), /Black Bolt/);
  assert.match(detailValue(renderer), /\$3,589\.70/);
  // Still exactly one chart: the selection moved it, it did not add one.
  assert.equal(charts(renderer).length, 1);
  // And the row reports its own selected state to assistive tech.
  const selected = rows(renderer).filter((node) => node.props["aria-current"] === "true");
  assert.deepEqual(selected.map((node) => node.props["data-set-market-row"]), ["set-c"]);
});

test("every row is a real button, so the list is keyboard navigable", () => {
  const renderer = render();
  for (const row of rows(renderer)) {
    assert.equal(row.type, "button");
    assert.equal(row.props.type, "button");
    assert.match(textOf(row), /Select .* to inspect its Set Market analysis\./);
  }
});

test("search narrows the list without repointing the analysis pane", () => {
  const renderer = render();
  const search = renderer.root.findAll((node) => node.props?.type === "search")[0];
  TestRenderer.act(() => { search.props.onChange({ target: { value: "black" } }); });

  assert.deepEqual(rows(renderer).map((node) => node.props["data-set-market-row"]), ["set-c"]);
  // The user narrowed the list; they did not ask to inspect a different set.
  assert.match(detailName(renderer), /Ascended Heroes/);
  // Rank stays market-wide rather than renumbering to the filtered view.
  assert.match(textOf(rows(renderer)[0]), /#3/);
});

test("the era filter offers only eras the snapshot actually publishes", () => {
  const renderer = render();
  const selects = renderer.root.findAll((node) => node.type === "select");
  const eraOptions = selects[0].findAllByType("option").map((node) => textOf(node));
  assert.deepEqual(eraOptions, ["All Eras", "Mega Evolution", "Scarlet & Violet"]);
});

test("the sort control reorders without inventing a metric", () => {
  const renderer = render();
  const selects = renderer.root.findAll((node) => node.type === "select");
  TestRenderer.act(() => { selects[1].props.onChange({ target: { value: "name" } }); });
  assert.deepEqual(rows(renderer).map((node) => node.props["data-set-market-row"]), ["set-a", "set-c", "set-b"]);

  TestRenderer.act(() => { selects[1].props.onChange({ target: { value: "change" } }); });
  // Published 7D percentages: -2.0 (c) > -3.9 (b) > -11.8 (a).
  assert.deepEqual(rows(renderer).map((node) => node.props["data-set-market-row"]), ["set-c", "set-b", "set-a"]);
});

test("both timeframes default to 7D and the list column reports the published movement", () => {
  const renderer = render();
  const checked = renderer.root
    .findAll((node) => node.props?.["data-time-range-value"] !== undefined && node.props["aria-checked"] === true)
    .map((node) => node.props["data-time-range-value"]);
  assert.deepEqual(checked, ["7D", "7D"], "the list column and the detail chart both start at 7D");
  assert.match(textOf(rows(renderer)[0]), /▼11\.8%/);
});

test("changing the detail timeframe re-reads the published window, never a derived one", () => {
  const renderer = render();
  const buttons = renderer.root.findAll((node) => node.props?.["data-time-range-value"] === "lifetime");
  // The second radiogroup is the detail pane's.
  TestRenderer.act(() => { buttons[buttons.length - 1].props.onClick(); });
  const pane = textOf(detail(renderer));
  assert.match(pane, /\+\$120\.00 \(\+2\.1%\)/, "the lifetime movement is the backend's own amount and percent");
});

test("an empty or failed snapshot says so instead of rendering an empty shell", () => {
  assert.match(textOf(render({ targets: [], loadError: false }).toJSON()), /Sets appear once the current Market snapshot is available\./);
  assert.match(textOf(render({ targets: [], loadError: true }).toJSON()), /Set Market is temporarily unavailable\./);
});
