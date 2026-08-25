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

function render(
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

const findAll = (renderer, prop) => renderer.root.findAll((node) => node.props?.[prop] !== undefined, { deep: true });

function textOf(node) {
  if (node === null || node === undefined || node === false) return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  return (node.children || []).map(textOf).filter(Boolean).join(" ");
}

const pageText = (renderer) => textOf(renderer.toJSON());

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

test("the workspace renders exactly three parent-market selector cards", () => {
  const renderer = render();
  const cards = findAll(renderer, "data-market-explorer-card");
  assert.deepEqual(cards.map((card) => card.props["data-market-explorer-card"]), ["raw", "topChase", "sealedMarket"]);
  const text = pageText(renderer);
  for (const label of ["Raw Card Market", "Top 10 Chase Market", "Sealed Market"]) {
    assert.ok(text.includes(label), label);
  }
});

test("all three markets are selected by default", () => {
  const renderer = render();
  const workspace = findAll(renderer, "data-market-explorer-workspace")[0];
  assert.equal(workspace.props["data-market-explorer-selection"], "raw,topChase,sealedMarket");
  for (const card of findAll(renderer, "data-market-explorer-card")) {
    assert.equal(card.props["data-market-explorer-card-selected"], "true", card.props["data-market-explorer-card"]);
  }
});

test("the chart carries one line per selected market", () => {
  const renderer = render();
  const series = findAll(renderer, "data-market-performance-series");
  assert.deepEqual(series.map((node) => node.props["data-market-performance-series"]), ["raw", "topChase", "sealedMarket"]);
});

test("toggling a card removes and restores that series everywhere at once", () => {
  const renderer = render();
  click(renderer, "data-market-explorer-card", "topChase");

  const workspace = () => findAll(renderer, "data-market-explorer-workspace")[0];
  assert.equal(workspace().props["data-market-explorer-selection"], "raw,sealedMarket");
  assert.deepEqual(
    findAll(renderer, "data-market-performance-series").map((node) => node.props["data-market-performance-series"]),
    ["raw", "sealedMarket"]
  );
  assert.deepEqual(
    findAll(renderer, "data-market-explorer-legend-item").map((node) => node.props["data-market-explorer-legend-item"]),
    ["raw", "sealedMarket"]
  );
  assert.deepEqual(
    findAll(renderer, "data-market-explorer-detail-row").map((node) => node.props["data-market-explorer-detail-row"]),
    ["raw", "sealedMarket"]
  );

  click(renderer, "data-market-explorer-card", "topChase");
  assert.equal(workspace().props["data-market-explorer-selection"], "raw,topChase,sealedMarket");
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
  assert.equal(findAll(renderer, "data-market-performance-series").length, 3);

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
  const text = pageText(render());
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

test("three filter axes are live and Era claims no analytics", () => {
  const renderer = render();
  const axes = findAll(renderer, "data-market-explorer-filter-axis");
  assert.deepEqual(axes.map((node) => node.props["data-market-explorer-filter-axis"]),
    ["assetMarket", "cardSegment", "sealedFamily", "era"]);
  for (const axis of axes.slice(0, 3)) {
    assert.equal(axis.props["data-market-explorer-filter-available"], "true",
      axis.props["data-market-explorer-filter-axis"]);
  }
  assert.equal(axes[3].props["data-market-explorer-filter-available"], "false");

  const text = pageText(renderer);
  assert.ok(text.includes("Explore Segments"));
  assert.ok(text.includes("All Eras"));
  // Era is still a fabrication if named as selectable.
  for (const forbidden of ["Scarlet & Violet", "Sword & Shield", "Sun & Moon"]) {
    assert.ok(!text.includes(forbidden), `${forbidden} must not be offered yet`);
  }
});

// --- card-rarity submarkets (Phase 3) -------------------------------------

test("the Card Segment axis offers exactly the published rarities, grouped by parent", () => {
  const renderer = render();
  const groups = findAll(renderer, "data-market-explorer-filter-group");
  assert.deepEqual(groups.map((node) => node.props["data-market-explorer-filter-group"]), ["raw"]);
  const options = findAll(renderer, "data-market-explorer-filter-option")
    .map((node) => node.props["data-market-explorer-filter-option"]);
  assert.deepEqual(options, [
    "raw", "topChase", "sealedMarket",
    "card:raw:specialIllustrationRare", "card:raw:illustrationRare", "card:raw:ultraRare",
    "sealed:boosterBox", "sealed:eliteTrainerBox", "sealed:packs",
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

test("selecting a raw rarity overlays it and brings the Raw Card Market benchmark", () => {
  const renderer = render(overview, { market: "sealedMarket" });
  const workspace = () => findAll(renderer, "data-market-explorer-workspace")[0];
  assert.equal(workspace().props["data-market-explorer-series"], "sealedMarket");

  toggleFilterOption(renderer, "card:raw:specialIllustrationRare");
  assert.equal(workspace().props["data-market-explorer-series"],
    "raw,sealedMarket,card:raw:specialIllustrationRare");
  assert.deepEqual(
    findAll(renderer, "data-market-performance-series").map((n) => n.props["data-market-performance-series"]),
    ["raw", "sealedMarket", "card:raw:specialIllustrationRare"]
  );
});

test("multiple rarities overlay together against their parent", () => {
  const renderer = render(overview, {
    segments: "card:raw:specialIllustrationRare,card:raw:illustrationRare",
  });
  const workspace = findAll(renderer, "data-market-explorer-workspace")[0];
  assert.equal(workspace.props["data-market-explorer-series"],
    "raw,card:raw:specialIllustrationRare,card:raw:illustrationRare");
  assert.equal(findAll(renderer, "data-market-explorer-legend-item").length, 3);
});

test("card and sealed submarkets compare on one chart", () => {
  const renderer = render(overview, {
    segments: "card:raw:specialIllustrationRare,sealed:boosterBox",
  });
  assert.deepEqual(
    findAll(renderer, "data-market-performance-series").map((n) => n.props["data-market-performance-series"]),
    ["raw", "sealedMarket", "sealed:boosterBox", "card:raw:specialIllustrationRare"]
  );
});

test("rarity submarkets appear in the detail table like any other market", () => {
  const renderer = render(overview, { segments: "card:raw:illustrationRare" });
  const rows = findAll(renderer, "data-market-explorer-detail-row");
  assert.deepEqual(rows.map((n) => n.props["data-market-explorer-detail-row"]),
    ["raw", "card:raw:illustrationRare"]);
  const text = pageText(renderer);
  assert.ok(text.includes("$2,221.12"), "rarity tracked value");
  assert.ok(text.includes("118.15"), "rarity index");
  // Its OWN Since Tracking (+18.15%), not the shared-comparison -0.57%.
  const sinceTracking = rows[1].findAll(
    (node) => node.props?.["data-market-explorer-detail-change"] === "All", { deep: true }
  )[0];
  assert.match(textOf(sinceTracking.toJSON ? sinceTracking.toJSON() : sinceTracking), /18\.15%/);
});

test("the raw-card residual is stated rather than hidden", () => {
  const text = pageText(render());
  assert.ok(text.includes("Other Cards"));
  assert.ok(text.includes("$1,334.44"));
});

test("Chase rarity segments are stated as unpublished, not silently missing", () => {
  const renderer = render();
  assert.equal(findAll(renderer, "data-market-explorer-chase-segments-unavailable").length, 1);
  assert.ok(pageText(renderer).includes("Chase rarity segments are not published yet"));
  // And no Chase group appears in the filter.
  assert.ok(!pageText(renderer).includes("Chase Segments"));
});

test("the parent can be switched off while a rarity child stays charted", () => {
  const renderer = render(overview, { segments: "card:raw:specialIllustrationRare" });
  const workspace = () => findAll(renderer, "data-market-explorer-workspace")[0];
  assert.equal(workspace().props["data-market-explorer-series"], "raw,card:raw:specialIllustrationRare");
  click(renderer, "data-market-explorer-card", "raw");
  assert.equal(workspace().props["data-market-explorer-series"], "card:raw:specialIllustrationRare");
  assert.equal(findAll(renderer, "data-market-performance-series").length, 1);
  // Now the child is the last series and is locked.
  toggleFilterOption(renderer, "card:raw:specialIllustrationRare");
  assert.equal(workspace().props["data-market-explorer-series"], "card:raw:specialIllustrationRare");
});

test("a snapshot without cardSegments hides the axis instead of inventing one", () => {
  const renderer = render(overview, {}, SEALED_SERIES, []);
  const axis = renderer.root.findAll(
    (node) => node.props?.["data-market-explorer-filter-axis"] === "cardSegment", { deep: true }
  )[0];
  assert.equal(axis.props["data-market-explorer-filter-available"], "false");
  assert.ok(pageText(renderer).includes("All Card Segments"));
  assert.equal(findAll(renderer, "data-market-explorer-workspace")[0].props["data-market-explorer-series"],
    "raw,topChase,sealedMarket");
});

test("the existing Sealed axis is unchanged by the card axis", () => {
  const renderer = render(overview, { segments: "sealed:boosterBox" });
  const workspace = findAll(renderer, "data-market-explorer-workspace")[0];
  assert.equal(workspace.props["data-market-explorer-series"], "sealedMarket,sealed:boosterBox");
  assert.equal(workspace.props["data-market-explorer-segment-ids"], "");
  assert.ok(pageText(renderer).includes("Other Sealed"));
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
    "raw", "topChase", "sealedMarket",
    "card:raw:specialIllustrationRare", "card:raw:illustrationRare", "card:raw:ultraRare",
    "sealed:boosterBox", "sealed:eliteTrainerBox", "sealed:packs",
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

test("selecting a submarket overlays it and brings Total Sealed with it", () => {
  const renderer = render(overview, { market: "raw" });
  const workspace = () => findAll(renderer, "data-market-explorer-workspace")[0];
  assert.equal(workspace().props["data-market-explorer-series"], "raw");

  toggleFilterOption(renderer, "sealed:boosterBox");
  // The parent benchmark arrives with the child.
  assert.equal(workspace().props["data-market-explorer-series"], "raw,sealedMarket,sealed:boosterBox");
  assert.deepEqual(
    findAll(renderer, "data-market-performance-series").map((n) => n.props["data-market-performance-series"]),
    ["raw", "sealedMarket", "sealed:boosterBox"]
  );
  assert.deepEqual(
    findAll(renderer, "data-market-explorer-legend-item").map((n) => n.props["data-market-explorer-legend-item"]),
    ["raw", "sealedMarket", "sealed:boosterBox"]
  );
});

test("multiple submarkets overlay together with their parent", () => {
  const renderer = render(overview, { segments: "sealed:boosterBox,sealed:packs" });
  const workspace = findAll(renderer, "data-market-explorer-workspace")[0];
  assert.equal(workspace.props["data-market-explorer-series"], "sealedMarket,sealed:boosterBox,sealed:packs");
  assert.deepEqual(
    findAll(renderer, "data-market-performance-series").map((n) => n.props["data-market-performance-series"]),
    ["sealedMarket", "sealed:boosterBox", "sealed:packs"]
  );
});

test("submarkets appear in the detail table exactly like parent markets", () => {
  const renderer = render(overview, { segments: "sealed:boosterBox" });
  const rows = findAll(renderer, "data-market-explorer-detail-row");
  assert.deepEqual(rows.map((n) => n.props["data-market-explorer-detail-row"]), ["sealedMarket", "sealed:boosterBox"]);
  const text = pageText(renderer);
  assert.ok(text.includes("$4,665.70"), "submarket tracked value");
  assert.ok(text.includes("99.01"), "submarket index");
  // Its OWN Since Tracking (-0.99%), not the shared-comparison -2.02%.
  const child = rows[1];
  const sinceTracking = child.findAll((node) => node.props?.["data-market-explorer-detail-change"] === "All", { deep: true })[0];
  assert.match(textOf(sinceTracking.toJSON ? sinceTracking.toJSON() : sinceTracking), /0\.99%/);
});

test("the residual is stated rather than folded into a published submarket", () => {
  const text = pageText(render());
  assert.ok(text.includes("Other Sealed"));
  assert.ok(text.includes("$2,506.78"));
});

test("the last remaining series cannot be deselected from the submarket axis either", () => {
  const renderer = render(overview, { segments: "sealed:boosterBox" });
  const workspace = () => findAll(renderer, "data-market-explorer-workspace")[0];
  // Turn the parent off, leaving only the child on the chart.
  click(renderer, "data-market-explorer-card", "sealedMarket");
  assert.equal(workspace().props["data-market-explorer-series"], "sealed:boosterBox");
  // Now the child is locked.
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
  assert.ok(pageText(renderer).includes("All Sealed Products"));
  assert.equal(findAll(renderer, "data-market-explorer-workspace")[0].props["data-market-explorer-series"], "raw,topChase,sealedMarket");
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

test("a snapshot without Sealed still renders Raw and Top Chase and does not crash", () => {
  const renderer = render(overviewNoSealed);
  assert.equal(findAll(renderer, "data-market-explorer-workspace")[0].props["data-market-explorer-selection"], "raw,topChase");
  assert.deepEqual(findAll(renderer, "data-market-performance-series").map((n) => n.props["data-market-performance-series"]), ["raw", "topChase"]);

  const sealedCard = renderer.root.findAll((node) => node.props?.["data-market-explorer-card"] === "sealedMarket", { deep: true })[0];
  assert.equal(sealedCard.props["data-market-explorer-card-available"], "false");
  assert.ok(pageText(renderer).includes("Not published in the current market snapshot."));
  // And it never appears in the detail strip as a market with values.
  assert.deepEqual(
    findAll(renderer, "data-market-explorer-detail-row").map((n) => n.props["data-market-explorer-detail-row"]),
    ["raw", "topChase"]
  );
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
