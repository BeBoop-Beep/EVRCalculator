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

test("detail mounts at most one chart while the selected history loads — never one per row", () => {
  const renderer = render();
  assert.ok(charts(renderer).length <= 1, "a 167-set catalogue must not mount 167 charts");
  const skeletons = renderer.root.findAll((node) => node.props?.["data-set-market-detail-skeleton"] !== undefined);
  assert.equal(skeletons.length, 1, "the selected-set request reserves one silent chart skeleton");
  assert.equal(skeletons[0].props["aria-hidden"], "true");
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
  // Still at most one chart: the selection moved it, it did not add one.
  assert.ok(charts(renderer).length <= 1);
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
  const trigger = renderer.root.find((node) => node.type === "button" && node.props["aria-label"] === "Filter by era");
  TestRenderer.act(() => { trigger.props.onClick(); });
  const eraOptions = renderer.root.findAll((node) => node.props?.role === "option").map((node) => textOf(node).replace(/\s*✓$/, ""));
  assert.deepEqual(eraOptions, ["All Eras", "Mega Evolution", "Scarlet & Violet"]);
});

test("the sort control reorders without inventing a metric", () => {
  const renderer = render();
  const openSort = () => renderer.root.find((node) => node.type === "button" && node.props["aria-label"] === "Sort sets").props.onClick();
  TestRenderer.act(openSort);
  TestRenderer.act(() => { renderer.root.findAll((node) => node.props?.role === "option").find((node) => textOf(node) === "Sort: Set Name").props.onClick(); });
  assert.deepEqual(rows(renderer).map((node) => node.props["data-set-market-row"]), ["set-a", "set-c", "set-b"]);

  TestRenderer.act(openSort);
  TestRenderer.act(() => { renderer.root.findAll((node) => node.props?.role === "option").find((node) => textOf(node) === "Sort: Change").props.onClick(); });
  // Published 7D percentages: -2.0 (c) > -3.9 (b) > -11.8 (a).
  assert.deepEqual(rows(renderer).map((node) => node.props["data-set-market-row"]), ["set-c", "set-b", "set-a"]);
});

// useMediaQuery answers `true` for (min-width: 1200px) on the first paint, so
// react-test-renderer sees the master-detail composition — the one where the
// timeframe is shared.
const checkedWindows = (renderer) => renderer.root
  .findAll((node) => node.props?.["data-time-range-value"] !== undefined && node.props["aria-checked"] === true)
  .map((node) => node.props["data-time-range-value"]);

test("the master-detail composition offers exactly ONE timeframe control", () => {
  const renderer = render();
  // Two selectors for one concept, visible at once, is an ambiguity rather
  // than a feature. The detail pane's copy is not rendered at all up here —
  // hiding it with CSS would leave a second radiogroup in the accessibility
  // tree announcing the same setting.
  const groups = renderer.root.findAll((node) => node.props?.role === "radiogroup");
  assert.equal(groups.length, 1, "one radiogroup, in the toolbar");
  assert.deepEqual(checkedWindows(renderer), ["7D"], "and it starts at 7D");
  assert.match(textOf(rows(renderer)[0]), /▼11\.8%/);
});

test("the shared timeframe moves the list AND the selected set together", () => {
  const renderer = render();
  const header = () => textOf(renderer.root.findAll((node) => node.props?.["data-set-market-list"] !== undefined)[0]);
  const detailWindow = () => renderer.root
    .findAll((node) => node.props?.["data-set-market-detail-window"] !== undefined)[0]
    .props["data-set-market-detail-window"];

  // Default: everything on 7D.
  assert.match(header(), /Set value \/ 7D/);
  assert.equal(detailWindow(), "7D");
  assert.match(textOf(rows(renderer)[0]), /▼11\.8%/);

  // One control, and every timeframe-dependent figure follows it: the list
  // header, the row deltas, the selected set's change, its label and its chart
  // (which reads the same movement object).
  const to30D = renderer.root.find((node) => node.props?.["data-time-range-value"] === "30D");
  TestRenderer.act(() => { to30D.props.onClick(); });
  assert.match(header(), /Set value \/ 30D/);
  assert.equal(detailWindow(), "30D");
  assert.match(textOf(rows(renderer)[0]), /▼0\.7%/, "the row now reports its 30D delta");
  const pane = textOf(renderer.root.findAll((node) => node.props?.["data-set-market-detail"] !== undefined)[0]);
  assert.match(pane, /-\$40\.00 \(-0\.7%\)/, "the selected set's own 30D movement");
  assert.match(pane, /Set Value · 30D/);
});

test("changing the selected set preserves the shared timeframe", () => {
  const renderer = render();
  TestRenderer.act(() => { renderer.root.find((node) => node.props?.["data-time-range-value"] === "1D").props.onClick(); });
  assert.deepEqual(checkedWindows(renderer), ["1D"]);

  // The window is a property of the workspace, not of the row you clicked.
  const blackBolt = rows(renderer).find((node) => node.props["data-set-market-row"] === "set-c");
  TestRenderer.act(() => { blackBolt.props.onClick(); });
  assert.deepEqual(checkedWindows(renderer), ["1D"], "selecting a set must not reset the timeframe");
  assert.equal(
    renderer.root.findAll((node) => node.props?.["data-set-market-detail-window"] !== undefined)[0]
      .props["data-set-market-detail-window"],
    "1D"
  );
});

test("every window re-reads the published movement, never a derived one", () => {
  const renderer = render();
  TestRenderer.act(() => { renderer.root.find((node) => node.props?.["data-time-range-value"] === "lifetime").props.onClick(); });
  const pane = textOf(detail(renderer));
  assert.match(pane, /\+\$120\.00 \(\+2\.1%\)/, "the lifetime movement is the backend's own amount and percent");
  assert.match(pane, /Set Value · All/);
});

test("an empty or failed snapshot says so instead of rendering an empty shell", () => {
  assert.match(textOf(render({ targets: [], loadError: false }).toJSON()), /Sets appear once the current Market snapshot is available\./);
  assert.match(textOf(render({ targets: [], loadError: true }).toJSON()), /Set Market is temporarily unavailable\./);
});
