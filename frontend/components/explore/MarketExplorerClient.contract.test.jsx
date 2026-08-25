// Market Explorer — the rendered research workspace.
//
// The workspace has one job it must never get wrong: what is on the chart, the
// legend, the cards and the detail strip is always the SAME selection over the
// SAME published window, and every number in it came from the snapshot.

import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer from "react-test-renderer";
import { readFileSync } from "node:fs";

import MarketExplorerClient from "./MarketExplorerClient.jsx";
import { resolveInitialExplorerState } from "@/lib/explore/marketExplorerState.mjs";
import {
  resolveCardSegmentReconciliation,
  resolveCardSegmentSeries,
  resolveSealedSegmentReconciliation,
  resolveSealedSegmentSeries,
  resolveTopChaseSegmentStatus,
} from "@/lib/explore/marketExplorerSeries.mjs";
import { resolveMarketOverview } from "@/lib/explore/marketOverviewPresentation.mjs";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const change = (percent) => ({ available: true, percent, startDate: "2024-01-01", endDate: "2024-01-05", coverage: "full" });
const missing = () => ({ available: false, percent: null, startDate: null, endDate: "2024-01-05", coverage: "unavailable" });
const trend = (...values) => values.map((value, index) => [`2024-01-0${index + 1}`, value]);

const changeSet = (percent) => ({
  "1D": change(percent), "7D": change(percent), "30D": change(percent),
  "3M": change(percent), "6M": missing(), "1Y": missing(), SinceTracking: change(percent),
});

const COMPARISON_WINDOWS = {
  "1D": { targetStartDate: "2024-01-04", displayStartDate: "2024-01-04", displayEndDate: "2024-01-05", available: true },
  "7D": { targetStartDate: "2023-12-30", displayStartDate: "2024-01-01", displayEndDate: "2024-01-05", available: true },
  "30D": { targetStartDate: "2023-12-07", displayStartDate: "2024-01-01", displayEndDate: "2024-01-05", available: true },
  "3M": { targetStartDate: "2023-10-08", displayStartDate: "2024-01-01", displayEndDate: "2024-01-05", available: true },
  "6M": { targetStartDate: "2023-07-10", displayStartDate: "2024-01-01", displayEndDate: "2024-01-05", available: false },
  "1Y": { targetStartDate: "2023-01-06", displayStartDate: "2024-01-01", displayEndDate: "2024-01-05", available: false },
  SinceTracking: { targetStartDate: "2024-01-01", displayStartDate: "2024-01-01", displayEndDate: "2024-01-05", available: true },
};

function snapshot({ withSealed = true } = {}) {
  const marketOverview = {
    marketDate: "2024-01-05",
    comparisonWindows: COMPARISON_WINDOWS,
    coverage: { eligibleSetCount: 3, rawCardCount: 512, chaseCardCount: 30 },
    raw: {
      basketValue: 8123.45, indexValue: 102.25, historyStartDate: "2024-01-01",
      trend: trend(100, 101, 99.5, 101.75, 102.25),
      // Tracked Value moved very differently from price performance. If any of
      // it leaks into a chart, legend or change cell, the assertions fail.
      basketChanges: changeSet(41.41), changes: changeSet(-0.89),
    },
    topChase: {
      basketValue: 4011.1, indexValue: 96.5, historyStartDate: "2024-01-01",
      trend: trend(100, 98, 97, 96.75, 96.5),
      basketChanges: changeSet(52.52), changes: changeSet(-1.09),
    },
  };
  if (withSealed) {
    marketOverview.sealedMarket = {
      basketValue: 15550.25, indexValue: 106.18, historyStartDate: "2024-01-01",
      trend: trend(100, 103, 104, 105.5, 106.18),
      basketChanges: changeSet(63.63), changes: changeSet(-0.38),
    };
  }
  marketOverview.sealedSegments = SEALED_SEGMENTS;
  marketOverview.cardSegments = CARD_SEGMENTS;
  return { marketOverview };
}

// Published card-rarity submarkets. SIR and IR are available; Ultra Rare is
// published-but-gated; Hyper Rare is absent entirely. Top Chase rarity segments
// are published as explicitly unavailable with a stated reason.
const CARD_SEGMENTS = {
  contractVersion: "pokemon-card-segments-v1",
  raw: {
    definitions: {
      taxonomyVersion: "pokemon-card-rarity-taxonomy-v1",
      segments: [
        { key: "specialIllustrationRare", label: "Special Illustration Rare", definition: "Canonical SIR cards." },
        { key: "illustrationRare", label: "Illustration Rare", definition: "Canonical IR cards." },
      ],
    },
    reconciliation: {
      parentMarket: "raw",
      parentBasketValue: 8123.45,
      publishedSegmentBasketValue: 6789.01,
      residual: { key: "otherCards", label: "Other Cards", basketValue: 1334.44, cardCount: 2907 },
    },
    segments: {
      specialIllustrationRare: {
        key: "specialIllustrationRare", label: "Special Illustration Rare", parentMarket: "raw",
        available: true, definition: "Canonical SIR cards.",
        taxonomyVersion: "pokemon-card-rarity-taxonomy-v1",
        basketValue: 4567.89, indexValue: 95.03, historyStartDate: "2024-01-01",
        changes: changeSet(-1.29), familyChanges: changeSet(-4.97),
        trend: trend(100, 99, 97, 96, 95.03),
        metadata: { cardCount: 222, setCount: 22 },
      },
      illustrationRare: {
        key: "illustrationRare", label: "Illustration Rare", parentMarket: "raw",
        available: true, definition: "Canonical IR cards.",
        taxonomyVersion: "pokemon-card-rarity-taxonomy-v1",
        basketValue: 2221.12, indexValue: 118.15, historyStartDate: "2024-01-01",
        changes: changeSet(-0.57), familyChanges: changeSet(18.15),
        trend: trend(100, 106, 112, 116, 118.15),
        metadata: { cardCount: 492, setCount: 21 },
      },
      ultraRare: {
        key: "ultraRare", label: "Ultra Rare", parentMarket: "raw",
        available: false, unavailableReason: "below the published segment quality gate",
      },
    },
  },
  topChase: {
    available: false,
    segments: {},
    unavailableReason: "No per-date, per-card Top Chase membership authority exists.",
  },
};

// Published Sealed submarkets. Booster Boxes and Packs are available; Elite
// Trainer Boxes is published-but-unavailable, and Booster Bundles is absent
// entirely — the two ways a segment can fail to be selectable.
const SEALED_SEGMENTS = {
  definitions: {
    contractVersion: "pokemon-sealed-segments-v1",
    segments: [
      { key: "boosterBox", label: "Booster Boxes", definition: "Standard sealed Booster Boxes." },
      { key: "packs", label: "Packs", definition: "Loose and sleeved booster packs combined." },
    ],
  },
  reconciliation: {
    parentBasketValue: 15550.25,
    publishedSegmentBasketValue: 13043.47,
    residual: { key: "otherSealed", label: "Other Sealed", basketValue: 2506.78, productCount: 10 },
    eligibleProductCount: 139,
  },
  segments: {
    total: { key: "total", label: "Total Sealed", isParent: true, available: true },
    boosterBox: {
      key: "boosterBox", label: "Booster Boxes", available: true, isComposite: false,
      productFamilies: ["booster_box"], definition: "Standard sealed Booster Boxes.",
      basketValue: 4665.7, indexValue: 99.01, historyStartDate: "2024-01-01",
      changes: changeSet(-2.02), familyChanges: changeSet(-0.99),
      trend: trend(100, 99.5, 99.2, 99.01, 99.01),
      metadata: { eligibleProductCount: 15 },
    },
    packs: {
      key: "packs", label: "Packs", available: true, isComposite: true,
      productFamilies: ["loose_booster_pack", "sleeved_booster_pack"],
      definition: "Loose and sleeved booster packs combined.",
      basketValue: 8377.77, indexValue: 116.17, historyStartDate: "2024-01-01",
      changes: changeSet(3.03), familyChanges: changeSet(16.17),
      trend: trend(100, 110, 114, 116, 116.17),
      metadata: { eligibleProductCount: 37 },
    },
    eliteTrainerBox: {
      key: "eliteTrainerBox", label: "Elite Trainer Boxes", available: false,
      unavailableReason: "no eligible constituent history",
    },
  },
};

const overview = resolveMarketOverview(snapshot());
const overviewNoSealed = resolveMarketOverview(snapshot({ withSealed: false }));

const SEALED_SERIES = resolveSealedSegmentSeries(snapshot());
const RECONCILIATION = resolveSealedSegmentReconciliation(snapshot());
const CARD_SERIES = resolveCardSegmentSeries(snapshot());
const CARD_RECONCILIATION = resolveCardSegmentReconciliation(snapshot());
const CHASE_STATUS = resolveTopChaseSegmentStatus(snapshot());

function renderCollapsed(
  value = overview, searchParams = {}, sealedSegments = SEALED_SERIES, cardSegments = CARD_SERIES,
) {
  let renderer;
  TestRenderer.act(() => {
    renderer = TestRenderer.create(
      React.createElement(MarketExplorerClient, {
        overview: value,
        sealedSegments,
        cardSegments,
        reconciliation: RECONCILIATION,
        cardReconciliation: CARD_RECONCILIATION,
        topChaseSegmentStatus: CHASE_STATUS,
        initialState: resolveInitialExplorerState(value, searchParams, sealedSegments, cardSegments),
      })
    );
  });
  return renderer;
}

/** Every rail group EXCEPT the builder, which owns an async options request. */
const RAIL_GROUPS = ["cardRarities", "sealedFamilies", "eraSets", "benchmarks"];

function expandGroup(renderer, id) {
  const toggle = renderer.root.findAll(
    (entry) => entry.props?.["data-explorer-disclosure-toggle"] === id, { deep: true }
  )[0];
  if (!toggle) return false;
  const panel = renderer.root.findAll(
    (entry) => entry.props?.["data-explorer-disclosure"] === id, { deep: true }
  )[0];
  if (panel?.props?.["data-explorer-disclosure-open"] === "true") return false;
  TestRenderer.act(() => { toggle.props.onClick?.(); });
  return true;
}

/**
 * The rail opens COLLAPSED by design, so a test about what a group offers has
 * to open it first — exactly as the user does. `renderCollapsed` is the
 * first-load state; `render` is the state after the user opened the groups.
 */
function render(...args) {
  const renderer = renderCollapsed(...args);
  for (const id of RAIL_GROUPS) expandGroup(renderer, id);
  return renderer;
}

const findAll = (renderer, prop) => renderer.root.findAll((node) => node.props?.[prop] !== undefined, { deep: true });

function textOf(node) {
  if (node === null || node === undefined || node === false) return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  return (node.children || []).map(textOf).filter(Boolean).join(" ");
}

const pageText = (renderer) => textOf(renderer.toJSON());

/**
 * Every InfoPopover's copy. The residual/coverage methodology now lives in the
 * group headers' ⓘ rather than as standing paragraphs in the rail, and a
 * popover renders its text only once opened — so the contract is asserted on
 * the text the trigger carries.
 */
const infoText = (renderer) => renderer.root
  .findAll((node) => typeof node.props?.text === "string", { deep: true })
  .map((node) => node.props.text)
  .join(" | ");

function click(renderer, prop, value) {
  const node = renderer.root.findAll((entry) => entry.props?.[prop] === value, { deep: true })[0];
  TestRenderer.act(() => { node.props.onClick?.(); });
}

// Filter rows are real checkboxes, so they are toggled the way a user does it.
function toggleFilterOption(renderer, key) {
  const option = renderer.root.findAll(
    (entry) => entry.props?.["data-market-explorer-filter-option"] === key, { deep: true }
  )[0];
  const input = option.findAll((entry) => entry.type === "input", { deep: true })[0];
  TestRenderer.act(() => { input.props.onChange?.(); });
}

// --- selectors ------------------------------------------------------------

test("the workspace renders one selector card per published asset class", () => {
  const renderer = render();
  const cards = findAll(renderer, "data-market-explorer-card");
  // ASSET CLASSES only. Per-Set Chase is a benchmark, not an asset class, so
  // it no longer gets a top-level card.
  assert.deepEqual(cards.map((card) => card.props["data-market-explorer-card"]), ["raw", "sealedMarket"]);
  const text = pageText(renderer);
  for (const label of ["Raw Card Market", "Sealed Market"]) {
    assert.ok(text.includes(label), label);
  }
  // It is still reachable — under Benchmarks, by its Explorer name.
  assert.ok(text.includes("Benchmarks"));
  assert.ok(text.includes("Per-Set Chase Market"));
});

test("the published asset classes are selected by default, and nothing else", () => {
  const renderer = render();
  const workspace = findAll(renderer, "data-market-explorer-workspace")[0];
  // Per-Set Chase lives in a collapsed group; charting it by default would put
  // a line on screen whose control the user cannot see.
  assert.equal(workspace.props["data-market-explorer-selection"], "raw,sealedMarket");
  for (const card of findAll(renderer, "data-market-explorer-card")) {
    assert.equal(card.props["data-market-explorer-card-selected"], "true", card.props["data-market-explorer-card"]);
  }
});

test("the chart carries one line per selected market", () => {
  const renderer = render();
  const series = findAll(renderer, "data-market-performance-series");
  assert.deepEqual(series.map((node) => node.props["data-market-performance-series"]), ["raw", "sealedMarket"]);
});

test("toggling a card removes and restores that series everywhere at once", () => {
  const renderer = render();
  click(renderer, "data-market-explorer-card", "sealedMarket");

  const workspace = () => findAll(renderer, "data-market-explorer-workspace")[0];
  assert.equal(workspace().props["data-market-explorer-selection"], "raw");
  for (const prop of [
    "data-market-performance-series",
    "data-market-explorer-legend-item",
    "data-market-explorer-detail-row",
  ]) {
    assert.deepEqual(findAll(renderer, prop).map((node) => node.props[prop]), ["raw"], prop);
  }

  click(renderer, "data-market-explorer-card", "sealedMarket");
  assert.equal(workspace().props["data-market-explorer-selection"], "raw,sealedMarket");
});

// --- information architecture ---------------------------------------------

test("the rail opens with one visible group and four collapsed ones", () => {
  const renderer = renderCollapsed();
  const groups = findAll(renderer, "data-explorer-disclosure");
  assert.deepEqual(groups.map((node) => node.props["data-explorer-disclosure"]), [
    "cardRarities", "sealedFamilies", "eraSets", "benchmarks", "buildAMarket",
  ]);
  // EVERY one of them starts closed. The opening rail is the asset classes
  // plus five headers, not twenty-five checkboxes and two paragraphs.
  for (const group of groups) {
    assert.equal(group.props["data-explorer-disclosure-open"], "false",
      group.props["data-explorer-disclosure"]);
  }
  // Asset Market is not a disclosure at all: it is the page's premise.
  const axes = findAll(renderer, "data-market-explorer-filter-axis")
    .map((node) => node.props["data-market-explorer-filter-axis"]);
  assert.deepEqual(axes, ["assetMarket"]);
  // And no collapsed group's options are rendered underneath it.
  const options = findAll(renderer, "data-market-explorer-filter-option")
    .map((node) => node.props["data-market-explorer-filter-option"]);
  assert.deepEqual(options, ["raw", "sealedMarket", "gradedMarket"]);
});

test("every group header is a real, accessible disclosure button", () => {
  const renderer = renderCollapsed();
  for (const id of [...RAIL_GROUPS, "buildAMarket"]) {
    const toggle = renderer.root.findAll(
      (node) => node.props?.["data-explorer-disclosure-toggle"] === id, { deep: true }
    )[0];
    assert.equal(toggle.type, "button", id);
    assert.equal(toggle.props["aria-expanded"], false, id);
    assert.ok(String(toggle.props["aria-controls"] || "").length > 0, id);
  }
});

test("expanding a group is client-only — no market request is issued", () => {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = (...args) => { calls.push(args[0]); return Promise.reject(new Error("no network in test")); };
  try {
    const renderer = renderCollapsed();
    for (const id of RAIL_GROUPS) expandGroup(renderer, id);
    // Era & Sets reads the shared canonical OPTIONS payload, which the page
    // requests once regardless; expanding never queries a market.
    assert.ok(!calls.some((url) => String(url).includes("POST")));
  } finally {
    globalThis.fetch = original;
  }
});

test("Active Markets lists every charted series as a removable chip", () => {
  const renderer = render();
  const chips = findAll(renderer, "data-market-explorer-active-chip")
    .map((node) => node.props["data-market-explorer-active-chip"]);
  assert.deepEqual(chips, ["raw", "sealedMarket"]);

  click(renderer, "data-market-explorer-active-remove", "sealedMarket");
  assert.equal(
    findAll(renderer, "data-market-explorer-workspace")[0].props["data-market-explorer-selection"], "raw");
  // Nothing re-adds it: there is no automatic parent series any more.
  assert.deepEqual(
    findAll(renderer, "data-market-explorer-active-chip").map((n) => n.props["data-market-explorer-active-chip"]),
    ["raw"]);
});

test("exactly ONE market at a time is the constituents target", () => {
  const renderer = render();
  // Two markets are charted, and the workspace still names at most one detail
  // target — four selected markets must not produce four constituent tables.
  assert.equal(findAll(renderer, "data-market-explorer-active-chip").length, 2);
  const target = findAll(renderer, "data-market-explorer-workspace")[0]
    .props["data-market-explorer-detail-series"];
  assert.ok(!target.includes(","));
  // Each chip offers the control that names it, and its pressed state mirrors
  // the single active target rather than per-chip local state.
  const pressed = findAll(renderer, "data-market-explorer-active-inspect")
    .filter((node) => node.props["aria-pressed"] === true);
  assert.ok(pressed.length <= 1);
});

test("the final selected market cannot be deselected — the chart is never emptied by selection", () => {
  const renderer = render(overview, { market: "sealedMarket" });
  const workspace = () => findAll(renderer, "data-market-explorer-workspace")[0];
  assert.equal(workspace().props["data-market-explorer-selection"], "sealedMarket");

  const sealedCard = () => renderer.root.findAll((node) => node.props?.["data-market-explorer-card"] === "sealedMarket", { deep: true })[0];
  assert.equal(sealedCard().props["data-market-explorer-card-locked"], "true");
  click(renderer, "data-market-explorer-card", "sealedMarket");
  assert.equal(workspace().props["data-market-explorer-selection"], "sealedMarket");
  assert.equal(findAll(renderer, "data-market-performance-series").length, 1);

  // The filter checkbox is the same rule, expressed the same way.
  const option = renderer.root.findAll((node) => node.type === "input" && node.props?.checked === true, { deep: true })[0];
  assert.equal(option.props.disabled, true);
});

// --- query state ----------------------------------------------------------

test("?market= preselects only that market", () => {
  for (const key of ["raw", "topChase", "sealedMarket"]) {
    const renderer = render(overview, { market: key });
    assert.equal(findAll(renderer, "data-market-explorer-workspace")[0].props["data-market-explorer-selection"], key);
    assert.deepEqual(findAll(renderer, "data-market-performance-series").map((n) => n.props["data-market-performance-series"]), [key]);
  }
});

// --- timeframes -----------------------------------------------------------

test("the default timeframe is 7D and every canonical window is offered", () => {
  const renderer = render();
  assert.equal(findAll(renderer, "data-market-explorer-workspace")[0].props["data-market-explorer-timeframe"], "7D");
  const buttons = findAll(renderer, "data-market-window-value");
  assert.deepEqual(buttons.map((node) => node.props["data-market-window-value"]), ["1D", "7D", "30D", "3M", "6M", "1Y", "All"]);
  assert.equal(buttons.find((node) => node.props["data-market-window-value"] === "7D").props["aria-checked"], true);
});

test("All selects the Since Tracking window; a window the snapshot lacks stays disabled", () => {
  const renderer = render();
  const button = (key) => renderer.root.findAll((node) => node.props?.["data-market-window-value"] === key, { deep: true })[0];

  TestRenderer.act(() => { button("All").props.onClick(); });
  assert.equal(findAll(renderer, "data-market-explorer-workspace")[0].props["data-market-explorer-timeframe"], "All");
  assert.equal(findAll(renderer, "data-market-performance-series").length, 2);

  // 6M is published unavailable and must not be selectable.
  assert.equal(button("6M").props["data-market-window-available"], "false");
  assert.equal(button("6M").props.disabled, true);
});

test("the reported return follows the selected timeframe, not a neighbouring window", () => {
  const renderer = render(overview, { market: "raw" });
  const cell = () => renderer.root.findAll((node) => node.props?.["data-market-explorer-card-change"] !== undefined, { deep: true })[0];
  assert.equal(cell().props["data-market-explorer-card-change"], "7D");

  TestRenderer.act(() => {
    renderer.root.findAll((node) => node.props?.["data-market-window-value"] === "1D", { deep: true })[0].props.onClick();
  });
  assert.equal(cell().props["data-market-explorer-card-change"], "1D");
});

// --- values ---------------------------------------------------------------

test("cards and detail rows print the published values, never a recomputed one", () => {
  const renderer = render();
  // Per-Set Chase is a benchmark and is off by default; select it so all three
  // published markets are on the page.
  toggleFilterOption(renderer, "topChase");
  const text = pageText(renderer);
  // Published basket values and index values, verbatim.
  assert.ok(text.includes("$8,123.45"), "raw tracked value");
  assert.ok(text.includes("$4,011.10"), "top chase tracked value");
  assert.ok(text.includes("$15,550.25"), "sealed tracked value");
  assert.ok(text.includes("102.25") && text.includes("96.50") && text.includes("106.18"), "index values");
  // Published price-performance returns.
  assert.ok(text.includes("0.89%") && text.includes("1.09%") && text.includes("0.38%"), "returns");
  // The tracked-value series is a DIFFERENT published series and is never
  // charted or reported as price performance on this page.
  for (const forbidden of ["41.41", "52.52", "63.63"]) {
    assert.ok(!text.includes(forbidden), `${forbidden} is a basketChanges figure and must not appear as price performance`);
  }
});

test("the detail strip reports every published window for each selected market", () => {
  const renderer = render();
  const headings = findAll(renderer, "data-market-explorer-detail-heading").map((node) => node.props["data-market-explorer-detail-heading"]);
  assert.deepEqual(headings, ["1D", "7D", "30D", "3M", "All"]);
  assert.ok(pageText(renderer).includes("Since Tracking"));
});

// --- future filters -------------------------------------------------------

test("every rail axis is live once opened, in the documented order", () => {
  const renderer = render();
  const axes = findAll(renderer, "data-market-explorer-filter-axis");
  assert.deepEqual(axes.map((node) => node.props["data-market-explorer-filter-axis"]),
    ["assetMarket", "cardSegment", "sealedFamily", "era", "benchmark"]);
  for (const axis of axes) {
    assert.equal(axis.props["data-market-explorer-filter-available"], "true",
      axis.props["data-market-explorer-filter-axis"]);
  }

  const text = pageText(renderer);
  assert.ok(text.includes("Explore Segments"));
  assert.ok(text.includes("Add prepared market segments to the chart."));
  assert.ok(text.includes("Card Rarities"));
  assert.ok(text.includes("Sealed Product Families"));
  assert.ok(text.includes("Era & Sets"));
  assert.ok(text.includes("Benchmarks"));
  assert.ok(text.includes("Build a Market"));
  assert.ok(text.includes("Create a custom filtered market."));
});

test("no era name is invented by the frontend, and no Legacy bucket exists", () => {
  const renderer = render();
  const everything = `${pageText(renderer)} ${infoText(renderer)}`;
  // Eras come from the canonical filter-options service. With no payload
  // loaded, the tree is empty and names nothing.
  assert.ok(!everything.includes("Legacy"), "no Legacy label anywhere");
  assert.ok(!everything.includes("Legacy / Sword & Shield"));
  const source = readFileSync(new URL("./MarketExplorerEraSets.jsx", import.meta.url), "utf8");
  const scope = readFileSync(new URL("../../lib/explore/marketExplorerScope.mjs", import.meta.url), "utf8");
  for (const file of [source, scope]) {
    assert.ok(!/["\x27`]Legacy/.test(file), "no hardcoded Legacy era label");
    // And no hardcoded era roster either: the labels are the payload's.
    assert.ok(!file.includes("Sun & Moon"));
  }
  // The one era name that may appear in prose is the canonical spelling.
  assert.ok(!/Legacy\s*\/\s*Sword/.test(`${source} ${scope}`));
});

test("Era & Sets says plainly that a scope is not a chartable line", () => {
  const renderer = render();
  const everything = `${pageText(renderer)} ${infoText(renderer)}`;
  assert.ok(everything.includes("scope"));
  assert.ok(everything.includes("no standalone era or set index is published"));
});

// --- card-rarity submarkets (Phase 3) -------------------------------------

test("the Card Segment axis offers exactly the published rarities, grouped by parent", () => {
  const renderer = render();
  const groups = findAll(renderer, "data-market-explorer-filter-group");
  assert.deepEqual(groups.map((node) => node.props["data-market-explorer-filter-group"]), ["raw"]);
  const options = findAll(renderer, "data-market-explorer-filter-option")
    .map((node) => node.props["data-market-explorer-filter-option"]);
  assert.deepEqual(options, [
    "raw", "sealedMarket", "gradedMarket",
    "card:raw:specialIllustrationRare", "card:raw:illustrationRare", "card:raw:ultraRare",
    "sealed:boosterBox", "sealed:eliteTrainerBox", "sealed:packs",
    "topChase",
  ]);
  const text = pageText(renderer);
  assert.ok(text.includes("Raw Card Segments"), "the parent universe is named");
  assert.ok(text.includes("SIR") && text.includes("IR"));
  assert.ok(!text.includes("Double Rare"), "an unpublished rarity must not appear");
});

test("a rarity below the quality gate is shown but cannot be selected", () => {
  const renderer = render();
  const option = renderer.root.findAll(
    (node) => node.props?.["data-market-explorer-filter-option"] === "card:raw:ultraRare", { deep: true }
  )[0];
  assert.equal(option.props["data-market-explorer-filter-option-available"], "false");
  const input = option.findAll((node) => node.type === "input", { deep: true })[0];
  assert.equal(input.props.disabled, true);
});

test("selecting a raw rarity adds ONLY that rarity — no automatic parent", () => {
  const renderer = render(overview, { market: "sealedMarket" });
  const workspace = () => findAll(renderer, "data-market-explorer-workspace")[0];
  assert.equal(workspace().props["data-market-explorer-series"], "sealedMarket");

  toggleFilterOption(renderer, "card:raw:specialIllustrationRare");
  // Raw Card Market is NOT dragged along. This is the fast lane: the selection
  // means exactly what was clicked.
  assert.equal(workspace().props["data-market-explorer-series"],
    "sealedMarket,card:raw:specialIllustrationRare");
  assert.deepEqual(
    findAll(renderer, "data-market-performance-series").map((n) => n.props["data-market-performance-series"]),
    ["sealedMarket", "card:raw:specialIllustrationRare"]
  );
});

test("SIR alone charts one line; SIR vs Raw is a second deliberate click", () => {
  const renderer = render(overview, { segments: "card:raw:specialIllustrationRare" });
  const workspace = () => findAll(renderer, "data-market-explorer-workspace")[0];
  assert.equal(workspace().props["data-market-explorer-series"], "card:raw:specialIllustrationRare");
  assert.equal(findAll(renderer, "data-market-performance-series").length, 1);

  toggleFilterOption(renderer, "raw");
  assert.equal(workspace().props["data-market-explorer-series"], "raw,card:raw:specialIllustrationRare");
  assert.equal(findAll(renderer, "data-market-performance-series").length, 2);
});

test("multiple rarities overlay together, and only those rarities", () => {
  const renderer = render(overview, {
    segments: "card:raw:specialIllustrationRare,card:raw:illustrationRare",
  });
  const workspace = findAll(renderer, "data-market-explorer-workspace")[0];
  assert.equal(workspace.props["data-market-explorer-series"],
    "card:raw:specialIllustrationRare,card:raw:illustrationRare");
  assert.equal(findAll(renderer, "data-market-explorer-legend-item").length, 2);
});

test("card and sealed submarkets compare on one chart", () => {
  const renderer = render(overview, {
    segments: "card:raw:specialIllustrationRare,sealed:boosterBox",
  });
  assert.deepEqual(
    findAll(renderer, "data-market-performance-series").map((n) => n.props["data-market-performance-series"]),
    ["sealed:boosterBox", "card:raw:specialIllustrationRare"]
  );
});

test("rarity submarkets appear in the detail table like any other market", () => {
  const renderer = render(overview, { segments: "card:raw:illustrationRare" });
  const rows = findAll(renderer, "data-market-explorer-detail-row");
  assert.deepEqual(rows.map((n) => n.props["data-market-explorer-detail-row"]),
    ["card:raw:illustrationRare"]);
  const text = pageText(renderer);
  assert.ok(text.includes("$2,221.12"), "rarity tracked value");
  assert.ok(text.includes("118.15"), "rarity index");
  // Its OWN Since Tracking (+18.15%), not the shared-comparison -0.57%.
  const sinceTracking = rows[0].findAll(
    (node) => node.props?.["data-market-explorer-detail-change"] === "All", { deep: true }
  )[0];
  assert.match(textOf(sinceTracking.toJSON ? sinceTracking.toJSON() : sinceTracking), /18\.15%/);
});

test("the raw-card residual is stated in the group's info, not as a wall of copy", () => {
  const renderer = render();
  const info = infoText(renderer);
  assert.ok(info.includes("Other Cards"));
  assert.ok(info.includes("$1,334.44"));
  assert.ok(info.includes("taxonomy is backend-defined"));
  // It is no longer a standing paragraph between the checkboxes.
  assert.equal(findAll(renderer, "data-market-explorer-card-residual").length, 0);
  assert.ok(!pageText(renderer).includes("$1,334.44"));
});

test("Chase rarity segments are stated as unpublished, not silently missing", () => {
  const renderer = render();
  // The reason moved into the Card Rarities ⓘ, with the rest of that group's
  // methodology, instead of standing under the checkbox list.
  assert.ok(infoText(renderer).includes("Chase rarity segments are not published"));
  // And no Chase group appears in the filter.
  assert.ok(!pageText(renderer).includes("Chase Segments"));
});

test("a lone rarity child is the last series and is locked", () => {
  const renderer = render(overview, { segments: "card:raw:specialIllustrationRare" });
  const workspace = () => findAll(renderer, "data-market-explorer-workspace")[0];
  assert.equal(workspace().props["data-market-explorer-series"], "card:raw:specialIllustrationRare");
  assert.equal(findAll(renderer, "data-market-performance-series").length, 1);
  toggleFilterOption(renderer, "card:raw:specialIllustrationRare");
  assert.equal(workspace().props["data-market-explorer-series"], "card:raw:specialIllustrationRare");
});

test("a snapshot without cardSegments hides the axis instead of inventing one", () => {
  const renderer = render(overview, {}, SEALED_SERIES, []);
  const axis = renderer.root.findAll(
    (node) => node.props?.["data-market-explorer-filter-axis"] === "cardSegment", { deep: true }
  )[0];
  assert.equal(axis.props["data-market-explorer-filter-available"], "false");
  assert.ok(pageText(renderer).includes("No card rarity submarkets are published"));
  assert.equal(findAll(renderer, "data-market-explorer-workspace")[0].props["data-market-explorer-series"],
    "raw,sealedMarket");
});

test("the existing Sealed axis is unchanged by the card axis", () => {
  const renderer = render(overview, { segments: "sealed:boosterBox" });
  const workspace = findAll(renderer, "data-market-explorer-workspace")[0];
  assert.equal(workspace.props["data-market-explorer-series"], "sealed:boosterBox");
  assert.equal(workspace.props["data-market-explorer-segment-ids"], "");
  assert.ok(infoText(renderer).includes("Other Sealed"));
});

// --- Sealed product-family submarkets -------------------------------------

test("the Sealed Product Family axis offers exactly the published segments", () => {
  const renderer = render();
  const options = findAll(renderer, "data-market-explorer-filter-option")
    .map((node) => node.props["data-market-explorer-filter-option"]);
  // Parent markets, then the card submarkets, then the sealed ones - the same
  // order as the parent cards above. Booster Bundles is absent from the payload
  // and therefore absent here.
  assert.deepEqual(options, [
    "raw", "sealedMarket", "gradedMarket",
    "card:raw:specialIllustrationRare", "card:raw:illustrationRare", "card:raw:ultraRare",
    "sealed:boosterBox", "sealed:eliteTrainerBox", "sealed:packs",
    "topChase",
  ]);
  const text = pageText(renderer);
  assert.ok(text.includes("Booster Boxes"));
  assert.ok(text.includes("Packs"));
  assert.ok(!text.includes("Booster Bundles"), "an unpublished segment must not appear");
});

test("a published-but-unavailable segment cannot be selected", () => {
  const renderer = render();
  const option = renderer.root.findAll(
    (node) => node.props?.["data-market-explorer-filter-option"] === "sealed:eliteTrainerBox", { deep: true }
  )[0];
  assert.equal(option.props["data-market-explorer-filter-option-available"], "false");
  const input = option.findAll((node) => node.type === "input", { deep: true })[0];
  assert.equal(input.props.disabled, true);
});

test("selecting a submarket adds ONLY that submarket", () => {
  const renderer = render(overview, { market: "raw" });
  const workspace = () => findAll(renderer, "data-market-explorer-workspace")[0];
  assert.equal(workspace().props["data-market-explorer-series"], "raw");

  toggleFilterOption(renderer, "sealed:boosterBox");
  // Total Sealed does NOT arrive uninvited.
  assert.equal(workspace().props["data-market-explorer-series"], "raw,sealed:boosterBox");
  for (const prop of ["data-market-performance-series", "data-market-explorer-legend-item"]) {
    assert.deepEqual(findAll(renderer, prop).map((n) => n.props[prop]), ["raw", "sealed:boosterBox"], prop);
  }

  // And the benchmark comparison remains available as a second click.
  toggleFilterOption(renderer, "sealedMarket");
  assert.equal(workspace().props["data-market-explorer-series"], "raw,sealedMarket,sealed:boosterBox");
});

test("multiple submarkets overlay together, and only those submarkets", () => {
  const renderer = render(overview, { segments: "sealed:boosterBox,sealed:packs" });
  const workspace = findAll(renderer, "data-market-explorer-workspace")[0];
  assert.equal(workspace.props["data-market-explorer-series"], "sealed:boosterBox,sealed:packs");
  assert.deepEqual(
    findAll(renderer, "data-market-performance-series").map((n) => n.props["data-market-performance-series"]),
    ["sealed:boosterBox", "sealed:packs"]
  );
});

test("submarkets appear in the detail table exactly like parent markets", () => {
  const renderer = render(overview, { segments: "sealed:boosterBox" });
  const rows = findAll(renderer, "data-market-explorer-detail-row");
  assert.deepEqual(rows.map((n) => n.props["data-market-explorer-detail-row"]), ["sealed:boosterBox"]);
  const text = pageText(renderer);
  assert.ok(text.includes("$4,665.70"), "submarket tracked value");
  assert.ok(text.includes("99.01"), "submarket index");
  // Its OWN Since Tracking (-0.99%), not the shared-comparison -2.02%.
  const child = rows[0];
  const sinceTracking = child.findAll((node) => node.props?.["data-market-explorer-detail-change"] === "All", { deep: true })[0];
  assert.match(textOf(sinceTracking.toJSON ? sinceTracking.toJSON() : sinceTracking), /0\.99%/);
});

test("the sealed residual is stated in the group's info, not as a wall of copy", () => {
  const renderer = render();
  const info = infoText(renderer);
  assert.ok(info.includes("Other Sealed"));
  assert.ok(info.includes("$2,506.78"));
  assert.equal(findAll(renderer, "data-market-explorer-sealed-residual").length, 0);
  assert.ok(!pageText(renderer).includes("$2,506.78"));
});

test("the last remaining series cannot be deselected from the submarket axis either", () => {
  const renderer = render(overview, { segments: "sealed:boosterBox" });
  const workspace = () => findAll(renderer, "data-market-explorer-workspace")[0];
  assert.equal(workspace().props["data-market-explorer-series"], "sealed:boosterBox");
  // The child is the only series, so it is locked.
  toggleFilterOption(renderer, "sealed:boosterBox");
  assert.equal(workspace().props["data-market-explorer-series"], "sealed:boosterBox");
  assert.equal(findAll(renderer, "data-market-performance-series").length, 1);
});

test("a snapshot without sealedSegments hides the axis instead of inventing one", () => {
  const renderer = render(overview, {}, []);
  const axis = renderer.root.findAll(
    (node) => node.props?.["data-market-explorer-filter-axis"] === "sealedFamily", { deep: true }
  )[0];
  assert.equal(axis.props["data-market-explorer-filter-available"], "false");
  assert.ok(pageText(renderer).includes("No sealed product-family submarkets are published"));
  assert.equal(findAll(renderer, "data-market-explorer-workspace")[0].props["data-market-explorer-series"], "raw,sealedMarket");
});

// --- window semantics ------------------------------------------------------

test("the detail table labels the family column Since Tracking and reads that series", () => {
  const renderer = render(overview, { market: "raw" });
  const heading = renderer.root.findAll(
    (node) => node.props?.["data-market-explorer-detail-heading"] === "All", { deep: true }
  )[0];
  assert.equal(heading.props["data-market-explorer-detail-dimension"], "family");
  assert.ok(pageText(renderer).includes("Since Tracking"));
});

test("selecting All names the shared comparable span, never Since Tracking", () => {
  const renderer = render();
  TestRenderer.act(() => {
    renderer.root.findAll((node) => node.props?.["data-market-window-value"] === "All", { deep: true })[0].props.onClick();
  });
  const note = findAll(renderer, "data-market-explorer-shared-span-note");
  assert.equal(note.length, 1);
  assert.ok(pageText(renderer).includes("Since Comparable Start".toLowerCase())
    || pageText(renderer).includes("since comparable start"));
});

// --- degradation ----------------------------------------------------------

test("a snapshot without Sealed still renders Raw and does not crash", () => {
  const renderer = render(overviewNoSealed);
  assert.equal(findAll(renderer, "data-market-explorer-workspace")[0].props["data-market-explorer-selection"], "raw");
  assert.deepEqual(findAll(renderer, "data-market-performance-series").map((n) => n.props["data-market-performance-series"]), ["raw"]);

  // An unpublished asset class is an explicitly unavailable OPTION — a
  // different statement from silently omitting the market.
  const sealedOption = renderer.root.findAll(
    (node) => node.props?.["data-market-explorer-filter-option"] === "sealedMarket", { deep: true })[0];
  assert.equal(sealedOption.props["data-market-explorer-filter-option-available"], "false");
  // And it never appears in the detail strip as a market with values.
  assert.deepEqual(
    findAll(renderer, "data-market-explorer-detail-row").map((n) => n.props["data-market-explorer-detail-row"]),
    ["raw"]
  );
});

test("Graded Market is visible, disabled, and fabricates nothing", () => {
  const renderer = render();
  const graded = renderer.root.findAll(
    (node) => node.props?.["data-market-explorer-filter-option"] === "gradedMarket", { deep: true })[0];
  assert.equal(graded.props["data-market-explorer-filter-option-available"], "false");
  assert.equal(graded.findAll((node) => node.type === "input", { deep: true })[0].props.disabled, true);
  assert.ok(pageText(renderer).includes("Graded Market"));
  // No fabricated $0 basket, no fake index, and no PSA/CGC/BGS sub-hierarchy
  // built ahead of the analytics.
  const text = pageText(renderer);
  assert.ok(!text.includes("$0.00"));
  for (const forbidden of ["PSA", "CGC", "BGS"]) assert.ok(!text.includes(forbidden), forbidden);
  assert.ok(infoText(renderer).includes("No canonical graded analytics are published yet"));
  // It is never charted.
  assert.ok(!findAll(renderer, "data-market-performance-series")
    .some((node) => node.props["data-market-performance-series"] === "gradedMarket"));
});

test("no published market snapshot degrades to a stated message rather than a crash", () => {
  const renderer = render(null);
  assert.ok(pageText(renderer).includes("Market Explorer is temporarily unavailable"));
});

// --- methodology copy -----------------------------------------------------

test("the page explains Market Index without implying every constituent appreciated", () => {
  const text = pageText(render());
  assert.ok(text.includes("Market Index measures price performance from a base of 100 while neutralizing constituent additions and removals."));
  assert.ok(text.includes("above its own index base"));
  assert.ok(text.includes("not that every card or product in it rose"));
  assert.ok(text.includes("Tracked Value is the current dollar value of the tracked basket."));
  // And the two long windows are explained as DIFFERENT spans.
  assert.ok(text.includes("Since Tracking is measured from each market"));
  assert.ok(text.includes("common comparable start"));
});

// --- dense-comparison readability -----------------------------------------

test("the area fill thins out as series are added so eight lines stay separable", async () => {
  const { resolveAreaOpacity } = await import("./MarketPerformanceChart.jsx");
  // The homepage's three-line chart is unchanged.
  for (const count of [1, 2, 3]) assert.equal(resolveAreaOpacity(count), 0.16);
  // Beyond that the per-series fill divides down rather than stacking into one
  // opaque block.
  assert.ok(resolveAreaOpacity(4) < 0.16);
  assert.ok(resolveAreaOpacity(8) < resolveAreaOpacity(4));
  assert.ok(resolveAreaOpacity(8) >= 0.03, "never fully invisible");
  assert.equal(resolveAreaOpacity(0), 0.16);
});
