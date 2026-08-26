// Quick segment toggles — the Explore Segments panel.
//
// A published submarket that renders a normal-looking checkbox MUST toggle. The
// defect these tests pin was a silent no-op: `toggleSealed`/`toggleCardSegment`
// called `setSegmentIds` from INSIDE the `setAssetUniverse` updater, so React
// queued the nested setter twice (StrictMode double-invocation, and replaying
// the update queue from a base state) and the second application toggled the
// segment straight back off. Every quick segment looked enabled and did
// nothing.
//
// The fix is one atomic reducer. These tests therefore assert the property that
// makes the fix correct — replay safety — and not merely that a click works
// once in a permissive renderer.

import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";

import MarketExplorerClient from "./MarketExplorerClient.jsx";
import {
  EXPLORER_SELECTION_ACTIONS,
  reduceExplorerSelection,
} from "@/lib/explore/marketExplorerState.mjs";
import {
  resolveCardSegmentSeries,
  resolveSealedSegmentSeries,
} from "@/lib/explore/marketExplorerSeries.mjs";
import { resolveMarketOverview } from "@/lib/explore/marketOverviewPresentation.mjs";
import { resolveInitialExplorerState } from "@/lib/explore/marketExplorerState.mjs";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const window = (start, end) => ({
  targetStartDate: start, displayStartDate: start, displayEndDate: end, available: true,
});
const COMPARISON_WINDOWS = {
  "1D": window("2024-01-04", "2024-01-05"),
  "7D": window("2024-01-01", "2024-01-05"),
  "30D": window("2024-01-01", "2024-01-05"),
  "3M": window("2024-01-01", "2024-01-05"),
  // Deliberately unavailable: a market must not become unclickable because ONE
  // window cannot be compared (section 4).
  "6M": { ...window("2024-01-01", "2024-01-05"), available: false },
  "1Y": { ...window("2024-01-01", "2024-01-05"), available: false },
  SinceTracking: window("2024-01-01", "2024-01-05"),
};
const change = (percent) => ({ available: true, percent, startDate: "2024-01-01", endDate: "2024-01-05", coverage: "full" });
const missing = () => ({ available: false, percent: null, startDate: null, endDate: "2024-01-05", coverage: "unavailable" });
const changeSet = (percent) => ({
  "1D": change(percent), "7D": change(percent), "30D": change(percent), "3M": change(percent),
  "6M": missing(), "1Y": missing(), SinceTracking: change(percent),
});
const trend = (...values) => values.map((value, index) => [`2024-01-0${index + 1}`, value]);
const series = (indexValue) => ({
  basketValue: 1000, indexValue, historyStartDate: "2024-01-01",
  trend: trend(100, 101, 102, 103, indexValue),
  changes: changeSet(1.5), familyChanges: changeSet(1.5), basketChanges: changeSet(1.5),
  available: true,
});

// Every modern rarity and every sealed family the backend publishes today.
const CARD_KEYS = ["specialIllustrationRare", "illustrationRare", "ultraRare", "hyperRare", "doubleRare"];
const LEGACY_KEYS = ["rareUltra", "rareSecret", "rareRainbow", "rareHolo"];
const SEALED_KEYS = ["boosterBox", "eliteTrainerBox", "pokemonCenterEliteTrainerBox", "boosterBundle", "packs"];

const payload = () => ({
  marketOverview: {
    marketDate: "2024-01-05",
    comparisonWindows: COMPARISON_WINDOWS,
    coverage: { eligibleSetCount: 3, rawCardCount: 512, chaseCardCount: 30 },
    raw: series(104), topChase: series(97), sealedMarket: series(106),
    cardSegments: {
      contractVersion: "pokemon-card-segments-v1",
      raw: {
        segments: {
          ...Object.fromEntries(CARD_KEYS.map((key) => [key, { ...series(110), label: key, parentMarket: "raw" }])),
          // Published, but genuinely unbuildable. Must be visible and disabled
          // with a stated reason — never silently dropped.
          ...Object.fromEntries(LEGACY_KEYS.map((key) => [key, {
            label: key, available: false, unavailableReason: "no eligible constituent history",
          }])),
        },
        definitions: { segments: [] },
      },
    },
    sealedSegments: {
      segments: Object.fromEntries(SEALED_KEYS.map((key) => [key, { ...series(108), label: key }])),
      definitions: { segments: [] },
    },
  },
});

function mountClient() {
  const source = payload();
  const overview = resolveMarketOverview(source);
  const sealedSegments = resolveSealedSegmentSeries(source);
  const cardSegments = resolveCardSegmentSeries(source);
  const initialState = resolveInitialExplorerState(overview, {}, sealedSegments, cardSegments);
  let renderer;
  act(() => {
    renderer = TestRenderer.create(
      // StrictMode ON: this is what Next runs in development, and it is the
      // condition under which the old code silently cancelled every toggle.
      <React.StrictMode>
        <MarketExplorerClient
          overview={overview}
          sealedSegments={sealedSegments}
          cardSegments={cardSegments}
          initialState={initialState}
          // These tests are about TOGGLE BEHAVIOUR under StrictMode, so they
          // render as an entitled user. What each plan is allowed to see is a
          // separate contract, tested in MarketExplorerClient.contract.
          user={{ id: "u-premium", index_plan: "premium" }}
        />
      </React.StrictMode>
    );
  });
  // The rail opens COLLAPSED. A quick segment is one click away, not zero, so
  // every test here opens its group first — exactly as the user does.
  for (const id of ["cardRarities", "sealedFamilies", "benchmarks"]) {
    const toggle = renderer.root.findAll(
      (node) => node.props?.["data-explorer-disclosure-toggle"] === id, { deep: true }
    )[0];
    if (toggle) act(() => { toggle.props.onClick?.(); });
  }
  return { renderer, cardSegments, sealedSegments };
}

const workspace = (renderer) =>
  renderer.root.find((node) => node.props?.["data-market-explorer-workspace"] !== undefined).props;
const optionFor = (renderer, seriesId) =>
  renderer.root.findAll((node) => node.props?.["data-market-explorer-filter-option"] === seriesId)[0] || null;
const checkboxFor = (renderer, seriesId) => optionFor(renderer, seriesId)?.findAll((node) => node.type === "input")[0] || null;

const CARD_ATTR = "data-market-explorer-segment-ids";
const SEALED_ATTR = "data-market-explorer-sealed-family-ids";

const QUICK_SEGMENTS = [
  ...CARD_KEYS.map((key) => ({ seriesId: `card:raw:${key}`, attr: CARD_ATTR })),
  ...SEALED_KEYS.map((key) => ({ seriesId: `sealed:${key}`, attr: SEALED_ATTR })),
];

for (const { seriesId, attr } of QUICK_SEGMENTS) {
  test(`quick segment ${seriesId} toggles on and off`, () => {
    const { renderer } = mountClient();
    const checkbox = checkboxFor(renderer, seriesId);
    assert.ok(checkbox, `${seriesId} must render a real control`);
    assert.equal(checkbox.props.disabled, false, `${seriesId} is published and must be enabled`);

    const before = workspace(renderer)[attr];
    act(() => { checkboxFor(renderer, seriesId).props.onChange(); });
    const on = workspace(renderer)[attr];
    assert.notEqual(on, before, `${seriesId} must actually enter the selection — no silent no-op`);
    assert.ok(on.split(",").includes(seriesId));

    act(() => { checkboxFor(renderer, seriesId).props.onChange(); });
    assert.equal(workspace(renderer)[attr], before, `${seriesId} must toggle back off`);
  });
}

test("a quick segment adds ONLY itself — no parent tags along", () => {
  const { renderer } = mountClient();
  // Start from the default asset classes and take Sealed Market off, so the
  // test can see whether the toggle puts it back.
  act(() => { checkboxFor(renderer, "sealedMarket").props.onChange(); });
  const before = workspace(renderer)["data-market-explorer-selection"].split(",");
  assert.ok(!before.includes("sealedMarket"));

  act(() => { checkboxFor(renderer, "sealed:eliteTrainerBox").props.onChange(); });
  const parents = workspace(renderer)["data-market-explorer-selection"].split(",");
  // It stays off. A line the user deliberately removed must not reappear
  // because they clicked something else.
  assert.ok(!parents.includes("sealedMarket"),
    "the fast lane is literal: a child never drags its parent onto the chart");
  assert.ok(workspace(renderer)["data-market-explorer-sealed-family-ids"]
    .split(",").includes("sealed:eliteTrainerBox"));
});

test("a published-but-unbuildable segment is visible, disabled and explains itself", () => {
  const { renderer } = mountClient();
  for (const key of LEGACY_KEYS) {
    const option = optionFor(renderer, `card:raw:${key}`);
    assert.ok(option, `${key} is published and must not silently vanish from the panel`);
    assert.equal(option.props["data-market-explorer-filter-option-available"], "false");
    assert.equal(checkboxFor(renderer, `card:raw:${key}`).props.disabled, true,
      "a control that cannot do anything must not look like one that can");
  }
});

test("an unavailable timeframe does not make a market unselectable", () => {
  // 6M and 1Y are unavailable in this snapshot. Series-level availability and
  // window-level availability are different questions and must stay separate.
  const { renderer, cardSegments } = mountClient();
  assert.ok(cardSegments.every((entry) => CARD_KEYS.includes(entry.key.split(":").pop())
    ? entry.available === true : true), "a missing window must not gate the series");
  const checkbox = checkboxFor(renderer, "card:raw:illustrationRare");
  assert.equal(checkbox.props.disabled, false);
  act(() => { checkboxFor(renderer, "card:raw:illustrationRare").props.onChange(); });
  assert.ok(workspace(renderer)[CARD_ATTR].includes("card:raw:illustrationRare"));
});

// --- the property that makes the fix correct --------------------------------

const AVAILABLE = {
  assetKeys: ["raw", "topChase", "sealedMarket"],
  sealedFamilyIds: SEALED_KEYS.map((key) => `sealed:${key}`),
  cardSegmentIds: CARD_KEYS.map((key) => `card:raw:${key}`),
};
const EMPTY = { assetUniverse: [], sealedFamilyIds: [], segmentIds: [] };

test("the reducer is replay-safe: applying one action twice from the same base is idempotent", () => {
  // React may invoke a reducer more than once for a single dispatch. If the
  // result depended on how many times it ran, the toggle would cancel itself —
  // which is exactly the defect this replaces.
  for (const [type, seriesId] of [
    [EXPLORER_SELECTION_ACTIONS.toggleCardSegment, "card:raw:illustrationRare"],
    [EXPLORER_SELECTION_ACTIONS.toggleSealedFamily, "sealed:packs"],
    [EXPLORER_SELECTION_ACTIONS.toggleMarket, "raw"],
  ]) {
    const action = { type, seriesId, available: AVAILABLE };
    const once = reduceExplorerSelection(EMPTY, action);
    const twice = reduceExplorerSelection(EMPTY, action);
    assert.deepEqual(twice, once, `${seriesId}: replaying from the same base must give the same state`);
  }
});

test("the reducer still moves the whole selection in ONE state object", () => {
  // The parent is no longer supplied, but the reason the reducer exists is
  // unchanged: the selection is one value that moves in one pure step, so a
  // replayed update can never apply half of it.
  const next = reduceExplorerSelection(EMPTY, {
    type: EXPLORER_SELECTION_ACTIONS.toggleCardSegment,
    seriesId: "card:raw:ultraRare",
    available: AVAILABLE,
  });
  assert.deepEqual(next.segmentIds, ["card:raw:ultraRare"]);
  assert.deepEqual(next.assetUniverse, [], "a rarity click adds a rarity and nothing else");
  assert.deepEqual(next.sealedFamilyIds, []);
});

test("reconciliation is idempotent and preserves identity when nothing moved", () => {
  const selected = reduceExplorerSelection(EMPTY, {
    type: EXPLORER_SELECTION_ACTIONS.toggleSealedFamily,
    seriesId: "sealed:boosterBox",
    available: AVAILABLE,
  });
  const reconcile = { type: EXPLORER_SELECTION_ACTIONS.reconcile, available: AVAILABLE };
  const first = reduceExplorerSelection(selected, reconcile);
  assert.equal(first, selected, "an unchanged reconcile must not produce a new object, or effects loop");
  assert.equal(reduceExplorerSelection(first, reconcile), first);
});

test("an unknown action leaves the selection untouched", () => {
  assert.equal(reduceExplorerSelection(EMPTY, { type: "nonsense" }), EMPTY);
});
