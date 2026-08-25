// Market Explorer — workspace state model.
//
// Guards the four ways this page could lie or break:
//   * inventing a market the snapshot did not publish,
//   * recomputing a published number,
//   * reaching an empty chart through selection,
//   * honouring a query parameter for a market that does not exist.

import test from "node:test";
import assert from "node:assert/strict";

import {
  MARKET_EXPLORER_ASSET_KEYS,
  MARKET_EXPLORER_DEFAULT_TIMEFRAME,
  MARKET_EXPLORER_DETAIL_WINDOWS,
  MARKET_EXPLORER_FILTER_AXES,
  buildAssetUniverseModel,
  buildExplorerTimeframeOptions,
  parseMarketExplorerQuery,
  reconcileAssetUniverse,
  buildCardSegmentModel,
  resolveAvailableAssetKeys,
  resolveAvailableCardSegmentIds,
  resolveAvailableSealedFamilyIds,
  resolveExplorerTimeframe,
  resolveInitialExplorerState,
  resolveSelectedSeriesIds,
  serializeMarketExplorerQuery,
  toggleAssetUniverseKey,
  toggleCardSegmentId,
  toggleSealedFamilyId,
} from "./marketExplorerState.mjs";
import {
  CARD_SEGMENT_SERIES,
  SEALED_SEGMENT_SERIES,
  buildComparableSeries,
  buildExplorerChartModel,
  parseCardSeriesId,
  resolveCardSegmentReconciliation,
  resolveCardSegmentSeries,
  resolveSealedSegmentReconciliation,
  resolveSealedSegmentSeries,
  resolveTopChaseSegmentStatus,
} from "./marketExplorerSeries.mjs";
import { resolveMarketOverview } from "./marketOverviewPresentation.mjs";

const change = (percent) => ({ available: true, percent, startDate: "2024-01-01", endDate: "2024-01-05", coverage: "full" });
const missing = () => ({ available: false, percent: null, startDate: null, endDate: "2024-01-05", coverage: "unavailable" });
const trend = (a, b, c, d, e) => [["2024-01-01", a], ["2024-01-02", b], ["2024-01-03", c], ["2024-01-04", d], ["2024-01-05", e]];

const changeSet = (percent) => ({
  "1D": change(percent), "7D": change(percent), "30D": change(percent),
  "3M": change(percent), "6M": missing(), "1Y": missing(), SinceTracking: change(percent),
});

// Window availability is a BACKEND decision (`available` on the comparison
// window, plus a real change on every family). 6M and 1Y are deliberately
// published as unavailable here so the fallback path is exercised.
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
    coverage: { eligibleSetCount: 3, rawCardCount: 512, chaseCardCount: 30, sealedProductCount: 44 },
    raw: { basketValue: 8123.45, indexValue: 102.25, historyStartDate: "2024-01-01", trend: trend(100, 101, 99.5, 101.75, 102.25), basketChanges: changeSet(9.99), changes: changeSet(-0.89) },
    topChase: { basketValue: 4011.1, indexValue: 96.5, historyStartDate: "2024-01-01", trend: trend(100, 98, 97, 96.75, 96.5), basketChanges: changeSet(8.88), changes: changeSet(-1.09) },
  };
  if (withSealed) {
    marketOverview.sealedMarket = { basketValue: 15550.25, indexValue: 106.18, historyStartDate: "2024-01-01", trend: trend(100, 103, 104, 105.5, 106.18), basketChanges: changeSet(7.77), changes: changeSet(-0.38) };
  }
  return { marketOverview };
}

const overview = resolveMarketOverview(snapshot());
const overviewNoSealed = resolveMarketOverview(snapshot({ withSealed: false }));

test("all three canonical markets normalize into the workspace model", () => {
  assert.deepEqual(MARKET_EXPLORER_ASSET_KEYS, ["raw", "topChase", "sealedMarket"]);
  assert.deepEqual(resolveAvailableAssetKeys(overview), ["raw", "topChase", "sealedMarket"]);
  const entries = buildAssetUniverseModel(overview, ["raw", "topChase", "sealedMarket"]);
  assert.equal(entries.length, 3);
  assert.ok(entries.every((entry) => entry.available && entry.selected && entry.family));
  assert.deepEqual(entries.map((entry) => entry.label), ["Raw Card Market", "Top 10 Chase Market", "Sealed Market"]);
});

test("a missing Sealed family degrades safely rather than crashing or disappearing", () => {
  assert.deepEqual(resolveAvailableAssetKeys(overviewNoSealed), ["raw", "topChase"]);
  const entries = buildAssetUniverseModel(overviewNoSealed, ["raw", "topChase"]);
  // Still three cards — the Sealed one is explicitly unavailable, which is a
  // different statement from silently omitting the market.
  assert.equal(entries.length, 3);
  const sealed = entries.find((entry) => entry.key === "sealedMarket");
  assert.equal(sealed.available, false);
  assert.equal(sealed.selected, false);
  assert.equal(sealed.family, null);
  const state = resolveInitialExplorerState(overviewNoSealed, {});
  assert.deepEqual(state.assetUniverse, ["raw", "topChase"]);
});

test("the default selection is every published market", () => {
  assert.deepEqual(resolveInitialExplorerState(overview, {}).assetUniverse, ["raw", "topChase", "sealedMarket"]);
  assert.deepEqual(resolveInitialExplorerState(overview, undefined).assetUniverse, ["raw", "topChase", "sealedMarket"]);
});

test("?market= preselects exactly that market", () => {
  assert.deepEqual(resolveInitialExplorerState(overview, { market: "sealedMarket" }).assetUniverse, ["sealedMarket"]);
  assert.deepEqual(resolveInitialExplorerState(overview, { market: "raw" }).assetUniverse, ["raw"]);
  assert.deepEqual(resolveInitialExplorerState(overview, { market: "topChase" }).assetUniverse, ["topChase"]);
});

test("?markets= accepts a comma list and normalizes its order", () => {
  assert.deepEqual(resolveInitialExplorerState(overview, { markets: "sealedMarket,raw" }).assetUniverse, ["raw", "sealedMarket"]);
  assert.deepEqual(resolveInitialExplorerState(overview, { markets: "raw,sealedMarket" }).assetUniverse, ["raw", "sealedMarket"]);
  assert.deepEqual(resolveInitialExplorerState(overview, { market: ["raw", "topChase"] }).assetUniverse, ["raw", "topChase"]);
});

test("a URLSearchParams instance is read through the same one parser", () => {
  const params = new URLSearchParams("market=raw&market=sealedMarket");
  assert.deepEqual(parseMarketExplorerQuery(params).requestedAssetKeys, ["raw", "sealedMarket"]);
});

test("an unknown or unpublished market request falls back rather than emptying the chart", () => {
  assert.deepEqual(resolveInitialExplorerState(overview, { market: "sirIndex" }).assetUniverse, ["raw", "topChase", "sealedMarket"]);
  assert.deepEqual(resolveInitialExplorerState(overviewNoSealed, { market: "sealedMarket" }).assetUniverse, ["raw", "topChase"]);
});

test("toggling adds and removes markets, but the final one cannot be deselected", () => {
  const keys = ["raw", "topChase", "sealedMarket"];
  assert.deepEqual(toggleAssetUniverseKey(keys, "topChase", keys), ["raw", "sealedMarket"]);
  assert.deepEqual(toggleAssetUniverseKey(["raw"], "topChase", keys), ["raw", "topChase"]);
  // The last active series is locked; the result is the SAME selection.
  assert.deepEqual(toggleAssetUniverseKey(["raw"], "raw", keys), ["raw"]);
  assert.deepEqual(toggleAssetUniverseKey(["sealedMarket"], "sealedMarket", keys), ["sealedMarket"]);
  // A market the snapshot never published cannot be toggled on.
  assert.deepEqual(toggleAssetUniverseKey(["raw"], "sealedMarket", ["raw", "topChase"]), ["raw"]);
});

test("reconciling against a re-published snapshot never yields an empty selection", () => {
  assert.deepEqual(reconcileAssetUniverse(["raw", "sealedMarket"], ["raw", "topChase"]), ["raw"]);
  assert.deepEqual(reconcileAssetUniverse(["sealedMarket"], ["raw", "topChase"]), ["raw", "topChase"]);
});

test("timeframes are the canonical backend windows and default to 7D", () => {
  assert.equal(MARKET_EXPLORER_DEFAULT_TIMEFRAME, "7D");
  const options = buildExplorerTimeframeOptions(overview);
  assert.deepEqual(options.map((entry) => entry.key), ["1D", "7D", "30D", "3M", "6M", "1Y", "All"]);
  assert.equal(resolveInitialExplorerState(overview, {}).timeframe, "7D");
  // "All" maps to the backend's SinceTracking key, not a locally invented span.
  assert.equal(options.find((entry) => entry.key === "All").changeKey, "SinceTracking");
  assert.equal(resolveExplorerTimeframe(overview, "All"), "All");
});

test("a timeframe the snapshot cannot support falls back instead of charting a fake span", () => {
  // 6M and 1Y are published as unavailable in this fixture.
  assert.equal(buildExplorerTimeframeOptions(overview).find((entry) => entry.key === "6M").available, false);
  assert.equal(resolveExplorerTimeframe(overview, "6M"), "7D");
  assert.equal(resolveExplorerTimeframe(overview, "nonsense"), "7D");
});

test("published values are passed through verbatim — nothing is recalculated", () => {
  const [raw, chase, sealed] = buildAssetUniverseModel(overview, ["raw", "topChase", "sealedMarket"]);
  assert.equal(raw.family.basketValue, 8123.45);
  assert.equal(raw.family.indexValue, 102.25);
  assert.equal(raw.family.changes["7D"].percent, -0.89);
  assert.equal(chase.family.changes["7D"].percent, -1.09);
  assert.equal(sealed.family.indexValue, 106.18);
  assert.equal(sealed.family.changes["7D"].percent, -0.38);
  // The published index (106.18) and the published tracked-value change (7.77)
  // are different series and must never be conflated.
  assert.equal(sealed.family.basketChanges.SinceTracking.percent, 7.77);
  assert.notEqual(sealed.family.basketChanges.SinceTracking.percent, sealed.family.changes.SinceTracking.percent);
});

test("the state model carries the future filter axes without claiming their data", () => {
  const state = resolveInitialExplorerState(overview, {});
  assert.deepEqual(state.eraIds, []);
  assert.deepEqual(state.segmentIds, []);
  assert.deepEqual(state.sealedFamilyIds, []);

  const byId = new Map(MARKET_EXPLORER_FILTER_AXES.map((axis) => [axis.id, axis]));
  assert.deepEqual([...byId.keys()], ["assetMarket", "sealedFamily", "era", "cardSegment"]);
  assert.equal(byId.get("assetMarket").available, true);
  assert.equal(byId.get("assetMarket").options.length, 3);
  // Both submarket axes are live but DYNAMIC: they carry no compile-time
  // options at all, so they can only ever offer what the payload published.
  for (const id of ["sealedFamily", "cardSegment"]) {
    assert.equal(byId.get(id).available, true, id);
    assert.equal(byId.get(id).dynamic, true, id);
    assert.deepEqual(byId.get(id).options, [], id);
  }
  // Era stays unavailable AND carries zero options. A populated option list
  // there would be a fabricated index.
  assert.equal(byId.get("era").available, false);
  assert.deepEqual(byId.get("era").options, []);
});

test("no unbuilt segment name is presented as an analytical option", () => {
  const serialized = JSON.stringify(MARKET_EXPLORER_FILTER_AXES);
  for (const forbidden of ["SIR", "Booster Box", "Scarlet", "Sword", "Hyper Rare", "ETB"]) {
    assert.ok(!serialized.includes(forbidden), `${forbidden} must not be hardcoded as a selectable segment`);
  }
});

// --- card-rarity submarkets (Phase 3) -------------------------------------

const CARD_SEGMENTS_PAYLOAD = {
  contractVersion: "pokemon-card-segments-v1",
  raw: {
    definitions: {
      taxonomyVersion: "pokemon-card-rarity-taxonomy-v1",
      segments: [
        { key: "specialIllustrationRare", label: "Special Illustration Rare", definition: "Canonical SIR cards." },
        { key: "illustrationRare", label: "Illustration Rare", definition: "Canonical IR cards." },
        { key: "ultraRare", label: "Ultra Rare", definition: "Canonical Ultra Rare cards." },
      ],
    },
    reconciliation: {
      parentMarket: "raw",
      parentBasketValue: 39341.65,
      publishedSegmentBasketValue: 33533.52,
      residual: { key: "otherCards", label: "Other Cards", basketValue: 5808.13, cardCount: 2907 },
    },
    segments: {
      specialIllustrationRare: {
        key: "specialIllustrationRare", label: "Special Illustration Rare", parentMarket: "raw",
        available: true, definition: "Canonical SIR cards.",
        taxonomyVersion: "pokemon-card-rarity-taxonomy-v1",
        basketValue: 20798.03, indexValue: 95.03, historyStartDate: "2024-01-01",
        changes: changeSet(-1.29), familyChanges: changeSet(-4.97),
        trend: trend(100, 99, 97, 96, 95.03),
        metadata: { cardCount: 222, setCount: 22 },
      },
      illustrationRare: {
        key: "illustrationRare", label: "Illustration Rare", parentMarket: "raw",
        available: true, definition: "Canonical IR cards.",
        taxonomyVersion: "pokemon-card-rarity-taxonomy-v1",
        basketValue: 9882.26, indexValue: 118.15, historyStartDate: "2024-01-01",
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

const cardSeries = resolveCardSegmentSeries({
  marketOverview: { ...snapshot().marketOverview, cardSegments: CARD_SEGMENTS_PAYLOAD },
});

test("only published, available card rarities become selectable series", () => {
  assert.deepEqual(cardSeries.map((entry) => entry.key), [
    "card:raw:specialIllustrationRare", "card:raw:illustrationRare", "card:raw:ultraRare",
  ]);
  assert.deepEqual(resolveAvailableCardSegmentIds(cardSeries), [
    "card:raw:specialIllustrationRare", "card:raw:illustrationRare",
  ]);
  // A rarity that failed the quality gate stays visible AND unselectable.
  const ultra = cardSeries.find((entry) => entry.key === "card:raw:ultraRare");
  assert.equal(ultra.available, false);
  assert.match(ultra.unavailableReason, /quality gate/);
  assert.equal(ultra.indexValue, undefined);
  // Rarities the payload never mentioned are simply absent.
  assert.ok(!cardSeries.some((entry) => entry.key.includes("hyperRare")));
});

test("a card series id names the universe it measures", () => {
  assert.deepEqual(parseCardSeriesId("card:raw:specialIllustrationRare"),
    { parentMarket: "raw", backendKey: "specialIllustrationRare" });
  assert.deepEqual(parseCardSeriesId("card:topChase:specialIllustrationRare"),
    { parentMarket: "topChase", backendKey: "specialIllustrationRare" });
  assert.equal(parseCardSeriesId("sealed:boosterBox"), null);
  assert.equal(parseCardSeriesId("raw"), null);
  // A Raw SIR index and a Chase SIR index are different markets and can never
  // collide on one id.
  assert.notEqual("card:raw:specialIllustrationRare", "card:topChase:specialIllustrationRare");
});

test("card segments carry their parent market and taxonomy version", () => {
  const sir = cardSeries.find((entry) => entry.key === "card:raw:specialIllustrationRare");
  assert.equal(sir.parentMarket, "raw");
  assert.equal(sir.parentSeriesId, "raw");
  assert.equal(sir.group, "card");
  assert.equal(sir.taxonomyVersion, "pokemon-card-rarity-taxonomy-v1");
  assert.equal(sir.cardCount, 222);
  assert.equal(sir.setCount, 22);
  assert.match(sir.definition, /Canonical SIR cards/);
});

test("card segment values are read verbatim, never recomputed", () => {
  const sir = cardSeries.find((entry) => entry.key === "card:raw:specialIllustrationRare");
  assert.equal(sir.basketValue, 20798.03);
  assert.equal(sir.indexValue, 95.03);
  // The index level and its OWN Since Tracking reconcile: 95.03 is -4.97%.
  assert.equal(sir.familyChanges.SinceTracking.percent, -4.97);
  // ...and the shared-comparison series stays separate.
  assert.equal(sir.changes["7D"].percent, -1.29);
  assert.notEqual(sir.changes.SinceTracking.percent, sir.familyChanges.SinceTracking.percent);
});

test("card segments are grouped by parent market for the filter", () => {
  const groups = buildCardSegmentModel(cardSeries, ["card:raw:illustrationRare"]);
  assert.deepEqual(groups.map((group) => group.parentMarket), ["raw"]);
  assert.equal(groups[0].label, "Raw Card Segments");
  assert.deepEqual(groups[0].entries.map((entry) => entry.selected), [false, true, false]);
  // No Chase group is shown while no Chase segment is published.
  assert.ok(!groups.some((group) => group.parentMarket === "topChase"));
});

test("card submarket colors are a violet family, distinct from the sealed amber", () => {
  const rawParent = overview.families.find((family) => family.key === "raw");
  assert.ok(rawParent.color.startsWith("rgba(167,139,250"), "Raw keeps its violet identity");
  const colors = CARD_SEGMENT_SERIES.map((entry) => entry.color);
  assert.equal(new Set(colors).size, colors.length, "every rarity is distinguishable");
  for (const color of [...colors, rawParent.color]) {
    const [, red, green, blue] = color.match(/rgba\((\d+),(\d+),(\d+)/).map(Number);
    // Violet/purple: blue dominant, green lowest. The sealed palette is the
    // mirror (red dominant), so the two groups never collide, and neither can
    // be mistaken for the green/red performance vocabulary.
    assert.ok(blue >= red && red > green, `${color} is outside the card palette`);
  }
  for (const sealed of SEALED_SEGMENT_SERIES) {
    assert.ok(!colors.includes(sealed.color), "card and sealed palettes must not overlap");
  }
});

test("selecting a raw rarity brings the Raw Card Market benchmark", () => {
  const availableCards = resolveAvailableCardSegmentIds(cardSeries);
  const result = toggleCardSegmentId([], "card:raw:specialIllustrationRare", availableCards, {
    assetUniverse: ["sealedMarket"],
    availableAssetKeys: ["raw", "topChase", "sealedMarket"],
  });
  assert.deepEqual(result.segmentIds, ["card:raw:specialIllustrationRare"]);
  assert.deepEqual(result.assetUniverse, ["raw", "sealedMarket"]);
});

test("a chase rarity would bring the Top Chase benchmark instead", () => {
  const result = toggleCardSegmentId([], "card:topChase:specialIllustrationRare",
    ["card:topChase:specialIllustrationRare"], {
      assetUniverse: ["raw"],
      availableAssetKeys: ["raw", "topChase", "sealedMarket"],
    });
  assert.deepEqual(result.assetUniverse, ["raw", "topChase"]);
});

test("a card segment the snapshot never published cannot be toggled on", () => {
  const result = toggleCardSegmentId([], "card:raw:ultraRare",
    ["card:raw:specialIllustrationRare"], {
      assetUniverse: ["raw"], availableAssetKeys: ["raw"],
    });
  assert.deepEqual(result.segmentIds, []);
  assert.deepEqual(result.assetUniverse, ["raw"]);
});

test("the parent can be switched off while a rarity child stays on the chart", () => {
  const assets = toggleAssetUniverseKey(["raw"], "raw", ["raw", "topChase", "sealedMarket"], {
    sealedFamilyIds: [], segmentIds: ["card:raw:specialIllustrationRare"],
  });
  assert.deepEqual(assets, []);
  assert.deepEqual(resolveSelectedSeriesIds({
    assetUniverse: assets, sealedFamilyIds: [], segmentIds: ["card:raw:specialIllustrationRare"],
  }), ["card:raw:specialIllustrationRare"]);
});

test("the final series overall cannot be deselected from the card axis either", () => {
  const locked = toggleCardSegmentId(["card:raw:specialIllustrationRare"],
    "card:raw:specialIllustrationRare", ["card:raw:specialIllustrationRare"], {
      assetUniverse: [], availableAssetKeys: ["raw"], sealedFamilyIds: [],
    });
  assert.deepEqual(locked.segmentIds, ["card:raw:specialIllustrationRare"]);
});

test("?segments= carries both submarket axes through one parameter", () => {
  const state = resolveInitialExplorerState(
    overview,
    { segments: "card:raw:specialIllustrationRare,sealed:boosterBox" },
    sealedSeries, cardSeries,
  );
  assert.deepEqual(state.segmentIds, ["card:raw:specialIllustrationRare"]);
  assert.deepEqual(state.sealedFamilyIds, ["sealed:boosterBox"]);
  // Both parents arrive as benchmarks, and nothing else.
  assert.deepEqual(state.assetUniverse, ["raw", "sealedMarket"]);
});

test("the combined query round-trips through one serializer", () => {
  const query = serializeMarketExplorerQuery({
    assetUniverse: ["raw", "sealedMarket"],
    sealedFamilyIds: ["sealed:boosterBox"],
    segmentIds: ["card:raw:illustrationRare"],
  });
  assert.equal(query, "markets=raw,sealedMarket&segments=sealed:boosterBox,card:raw:illustrationRare");
  const reparsed = resolveInitialExplorerState(
    overview, new URLSearchParams(query), sealedSeries, cardSeries
  );
  assert.deepEqual(reparsed.assetUniverse, ["raw", "sealedMarket"]);
  assert.deepEqual(reparsed.sealedFamilyIds, ["sealed:boosterBox"]);
  assert.deepEqual(reparsed.segmentIds, ["card:raw:illustrationRare"]);
});

test("an unknown or unpublished segment id is dropped rather than charted", () => {
  const state = resolveInitialExplorerState(
    overview,
    { segments: "card:raw:nope,card:era:sv,sealed:nope" },
    sealedSeries, cardSeries,
  );
  assert.deepEqual(state.segmentIds, []);
  assert.deepEqual(state.sealedFamilyIds, []);
  assert.deepEqual(state.assetUniverse, ["raw", "topChase", "sealedMarket"]);
});

test("raw-card reconciliation is surfaced so the residual can be stated", () => {
  const reconciliation = resolveCardSegmentReconciliation({
    marketOverview: { ...snapshot().marketOverview, cardSegments: CARD_SEGMENTS_PAYLOAD },
  });
  assert.equal(reconciliation.parentBasketValue, 39341.65);
  assert.equal(reconciliation.publishedSegmentBasketValue, 33533.52);
  assert.equal(reconciliation.residualLabel, "Other Cards");
  assert.equal(reconciliation.residualBasketValue, 5808.13);
  assert.equal(
    Math.round((reconciliation.publishedSegmentBasketValue + reconciliation.residualBasketValue) * 100) / 100,
    reconciliation.parentBasketValue
  );
});

test("the unpublished Top Chase rarity axis states its reason", () => {
  const status = resolveTopChaseSegmentStatus({
    marketOverview: { ...snapshot().marketOverview, cardSegments: CARD_SEGMENTS_PAYLOAD },
  });
  assert.equal(status.available, false);
  assert.match(status.reason, /membership authority/i);
  assert.equal(resolveTopChaseSegmentStatus(snapshot()), null);
});

test("a snapshot with no cardSegments yields no card series at all", () => {
  assert.deepEqual(resolveCardSegmentSeries(snapshot()), []);
  assert.equal(resolveCardSegmentReconciliation(snapshot()), null);
  assert.deepEqual(resolveInitialExplorerState(overview, {}, [], []).segmentIds, []);
});

test("parents, sealed submarkets and card submarkets become one series list", () => {
  const all = buildComparableSeries(overview, sealedSeries, cardSeries);
  assert.deepEqual(all.map((entry) => entry.key), [
    "raw", "topChase", "sealedMarket",
    "sealed:boosterBox", "sealed:eliteTrainerBox", "sealed:packs",
    "card:raw:specialIllustrationRare", "card:raw:illustrationRare", "card:raw:ultraRare",
  ]);
  assert.equal(all.find((entry) => entry.key === "card:raw:illustrationRare").isParent, false);
});

test("the chart clips card submarkets to the same backend window as everything else", () => {
  const all = buildComparableSeries(overview, sealedSeries, cardSeries);
  const selected = all.filter((entry) => [
    "raw", "card:raw:specialIllustrationRare", "card:raw:illustrationRare",
    "sealedMarket", "sealed:boosterBox",
  ].includes(entry.key));
  const model = buildExplorerChartModel(overview, selected, "7D");
  assert.equal(model.available, true);
  assert.deepEqual(model.series.map((entry) => entry.key), [
    "raw", "sealedMarket", "sealed:boosterBox",
    "card:raw:specialIllustrationRare", "card:raw:illustrationRare",
  ]);
  assert.equal(model.startDate, "2024-01-01");
  assert.equal(model.endDate, "2024-01-05");
  for (const entry of model.series) {
    assert.equal(entry.values.length, model.dates.length, entry.key);
  }
});

test("the detail strip locks Since Tracking to the family-specific series", () => {
  const byKey = new Map(MARKET_EXPLORER_DETAIL_WINDOWS.map((entry) => [entry.key, entry]));
  // Every fixed window reads the shared cross-market domain...
  for (const key of ["1D", "7D", "30D", "3M"]) {
    assert.equal(byKey.get(key).dimension, "comparison", key);
  }
  // ...and only the Since Tracking column reads the family's own history.
  assert.equal(byKey.get("All").dimension, "family");
  assert.equal(byKey.get("All").label, "Since Tracking");
});

test("the detail strip reports the fixed published window set", () => {
  assert.deepEqual(MARKET_EXPLORER_DETAIL_WINDOWS.map((entry) => entry.key), ["1D", "7D", "30D", "3M", "All"]);
  assert.equal(MARKET_EXPLORER_DETAIL_WINDOWS.at(-1).label, "Since Tracking");
});

// --- Sealed product-family submarkets -------------------------------------

const SEALED_SEGMENTS_PAYLOAD = {
  definitions: {
    contractVersion: "pokemon-sealed-segments-v1",
    segments: [
      { key: "boosterBox", label: "Booster Boxes", definition: "Standard sealed Booster Boxes." },
      { key: "packs", label: "Packs", definition: "Loose and sleeved booster packs combined." },
    ],
  },
  reconciliation: {
    parentBasketValue: 22929.9,
    publishedSegmentBasketValue: 20423.12,
    residual: { key: "otherSealed", label: "Other Sealed", basketValue: 2506.78, productCount: 10 },
    eligibleProductCount: 139,
  },
  segments: {
    total: { key: "total", label: "Total Sealed", isParent: true, available: true },
    boosterBox: {
      key: "boosterBox", label: "Booster Boxes", available: true, isComposite: false,
      productFamilies: ["booster_box"], definition: "Standard sealed Booster Boxes.",
      basketValue: 4665.7, indexValue: 99.01, historyStartDate: "2024-01-01",
      changes: changeSet(-0.51), familyChanges: changeSet(-0.99),
      trend: trend(100, 99.5, 99.2, 99.01, 99.01),
      metadata: { eligibleProductCount: 15 },
    },
    packs: {
      key: "packs", label: "Packs", available: true, isComposite: true,
      productFamilies: ["loose_booster_pack", "sleeved_booster_pack"],
      definition: "Loose and sleeved booster packs combined.",
      basketValue: 421.66, indexValue: 116.17, historyStartDate: "2024-01-01",
      changes: changeSet(0.36), familyChanges: changeSet(16.17),
      trend: trend(100, 110, 114, 116, 116.17),
      metadata: { eligibleProductCount: 37 },
    },
    eliteTrainerBox: {
      key: "eliteTrainerBox", label: "Elite Trainer Boxes", available: false,
      unavailableReason: "no eligible constituent history",
    },
  },
};

const sealedSeries = resolveSealedSegmentSeries({
  marketOverview: { ...snapshot().marketOverview, sealedSegments: SEALED_SEGMENTS_PAYLOAD },
});

test("only published, available Sealed segments become selectable series", () => {
  assert.deepEqual(sealedSeries.map((entry) => entry.key), [
    "sealed:boosterBox", "sealed:eliteTrainerBox", "sealed:packs",
  ]);
  assert.deepEqual(resolveAvailableSealedFamilyIds(sealedSeries), [
    "sealed:boosterBox", "sealed:packs",
  ]);
  // The unpublished ETB segment survives as an explicit unavailable entry.
  const etb = sealedSeries.find((entry) => entry.key === "sealed:eliteTrainerBox");
  assert.equal(etb.available, false);
  assert.equal(etb.indexValue, undefined);
  // Segments the payload never mentioned are simply absent.
  assert.ok(!sealedSeries.some((entry) => entry.key === "sealed:boosterBundle"));
});

test("a snapshot with no sealedSegments yields no submarket series at all", () => {
  assert.deepEqual(resolveSealedSegmentSeries(snapshot()), []);
  assert.equal(resolveSealedSegmentReconciliation(snapshot()), null);
  assert.deepEqual(resolveInitialExplorerState(overview, {}, []).sealedFamilyIds, []);
});

test("submarket values are read verbatim, never recomputed", () => {
  const boosterBox = sealedSeries.find((entry) => entry.key === "sealed:boosterBox");
  assert.equal(boosterBox.basketValue, 4665.7);
  assert.equal(boosterBox.indexValue, 99.01);
  assert.equal(boosterBox.productCount, 15);
  // The two window vocabularies stay separate on submarkets too.
  assert.equal(boosterBox.changes["7D"].percent, -0.51);
  assert.equal(boosterBox.familyChanges.SinceTracking.percent, -0.99);
  assert.notEqual(
    boosterBox.changes.SinceTracking.percent,
    boosterBox.familyChanges.SinceTracking.percent
  );
});

test("a composite segment declares itself and names its families", () => {
  const packs = sealedSeries.find((entry) => entry.key === "sealed:packs");
  assert.equal(packs.isComposite, true);
  assert.deepEqual(packs.productFamilies, ["loose_booster_pack", "sleeved_booster_pack"]);
  assert.match(packs.definition, /loose and sleeved/i);
  const boosterBox = sealedSeries.find((entry) => entry.key === "sealed:boosterBox");
  assert.equal(boosterBox.isComposite, false);
});

test("submarket colors are a sealed family and never gain/loss colors", () => {
  const sealedParent = overview.families.find((family) => family.key === "sealedMarket");
  assert.ok(sealedParent.color.startsWith("rgba(251,191,36"), "parent keeps its amber identity");
  const colors = SEALED_SEGMENT_SERIES.map((entry) => entry.color);
  assert.equal(new Set(colors).size, colors.length, "every submarket is distinguishable");
  for (const color of [...colors, sealedParent.color]) {
    const [, red, green, blue] = color.match(/rgba\((\d+),(\d+),(\d+)/).map(Number);
    // Amber/orange family: red dominant, blue lowest. A green or red tone
    // would collide with the performance vocabulary.
    assert.ok(red >= green && green > blue, `${color} is outside the sealed palette`);
  }
});

test("selecting a submarket brings its parent benchmark onto the chart", () => {
  const availableSealed = resolveAvailableSealedFamilyIds(sealedSeries);
  // Start with only Raw selected — Total Sealed is not on the chart.
  const result = toggleSealedFamilyId([], "sealed:boosterBox", availableSealed, {
    assetUniverse: ["raw"],
    availableAssetKeys: ["raw", "topChase", "sealedMarket"],
  });
  assert.deepEqual(result.sealedFamilyIds, ["sealed:boosterBox"]);
  assert.deepEqual(result.assetUniverse, ["raw", "sealedMarket"]);

  // It supplies the parent, it does not re-force it: with the parent already
  // deliberately off, adding a second child leaves the user's choice alone
  // only after they remove it — here the parent is present, so nothing changes.
  const second = toggleSealedFamilyId(result.sealedFamilyIds, "sealed:packs", availableSealed, {
    assetUniverse: result.assetUniverse,
    availableAssetKeys: ["raw", "topChase", "sealedMarket"],
  });
  assert.deepEqual(second.assetUniverse, ["raw", "sealedMarket"]);
});

test("the parent can be switched off explicitly while children stay", () => {
  const assets = toggleAssetUniverseKey(["sealedMarket"], "sealedMarket", ["raw", "topChase", "sealedMarket"], {
    sealedFamilyIds: ["sealed:boosterBox"],
  });
  // The chart is not empty — a submarket is still on it — so the last parent
  // may legitimately be removed.
  assert.deepEqual(assets, []);
  assert.deepEqual(resolveSelectedSeriesIds({ assetUniverse: assets, sealedFamilyIds: ["sealed:boosterBox"] }), [
    "sealed:boosterBox",
  ]);
});

test("the final series overall cannot be deselected, whichever axis it is on", () => {
  const availableSealed = resolveAvailableSealedFamilyIds(sealedSeries);
  const locked = toggleSealedFamilyId(["sealed:boosterBox"], "sealed:boosterBox", availableSealed, {
    assetUniverse: [],
    availableAssetKeys: ["raw", "topChase", "sealedMarket"],
  });
  assert.deepEqual(locked.sealedFamilyIds, ["sealed:boosterBox"]);
  // And the same rule from the parent side.
  assert.deepEqual(toggleAssetUniverseKey(["raw"], "raw", ["raw"], { sealedFamilyIds: [] }), ["raw"]);
});

test("a submarket the snapshot never published cannot be toggled on", () => {
  const result = toggleSealedFamilyId([], "sealed:eliteTrainerBox", ["sealed:boosterBox"], {
    assetUniverse: ["raw"],
    availableAssetKeys: ["raw"],
  });
  assert.deepEqual(result.sealedFamilyIds, []);
  assert.deepEqual(result.assetUniverse, ["raw"]);
});

test("?segments= preselects submarkets against their parent benchmark", () => {
  const state = resolveInitialExplorerState(
    overview, { segments: "sealed:boosterBox,sealed:packs" }, sealedSeries
  );
  assert.deepEqual(state.sealedFamilyIds, ["sealed:boosterBox", "sealed:packs"]);
  // A submarket-only link lands on the parent benchmark, not all three markets.
  assert.deepEqual(state.assetUniverse, ["sealedMarket"]);
});

test("?market= and ?segments= combine, and unknown segments are dropped", () => {
  const state = resolveInitialExplorerState(
    overview, { market: "raw", segments: "sealed:boosterBox,sealed:nope,card:sir" }, sealedSeries
  );
  assert.deepEqual(state.assetUniverse, ["raw"]);
  assert.deepEqual(state.sealedFamilyIds, ["sealed:boosterBox"]);
});

test("the query round-trips through one serializer", () => {
  const query = serializeMarketExplorerQuery({
    assetUniverse: ["raw", "sealedMarket"],
    sealedFamilyIds: ["sealed:boosterBox"],
  });
  assert.equal(query, "markets=raw,sealedMarket&segments=sealed:boosterBox");
  const reparsed = resolveInitialExplorerState(overview, new URLSearchParams(query), sealedSeries);
  assert.deepEqual(reparsed.assetUniverse, ["raw", "sealedMarket"]);
  assert.deepEqual(reparsed.sealedFamilyIds, ["sealed:boosterBox"]);
});

test("reconciliation metadata is surfaced so the residual can be stated", () => {
  const reconciliation = resolveSealedSegmentReconciliation({
    marketOverview: { ...snapshot().marketOverview, sealedSegments: SEALED_SEGMENTS_PAYLOAD },
  });
  assert.equal(reconciliation.parentBasketValue, 22929.9);
  assert.equal(reconciliation.publishedSegmentBasketValue, 20423.12);
  assert.equal(reconciliation.residualLabel, "Other Sealed");
  assert.equal(reconciliation.residualBasketValue, 2506.78);
  // Published + residual is the parent, exactly.
  assert.equal(
    Math.round((reconciliation.publishedSegmentBasketValue + reconciliation.residualBasketValue) * 100) / 100,
    reconciliation.parentBasketValue
  );
});

test("parents and submarkets become one comparable series list", () => {
  const all = buildComparableSeries(overview, sealedSeries);
  assert.deepEqual(all.map((entry) => entry.key), [
    "raw", "topChase", "sealedMarket",
    "sealed:boosterBox", "sealed:eliteTrainerBox", "sealed:packs",
  ]);
  assert.equal(all.find((entry) => entry.key === "raw").group, "card");
  assert.equal(all.find((entry) => entry.key === "sealedMarket").group, "sealed");
  assert.equal(all.find((entry) => entry.key === "sealed:packs").group, "sealed");
  assert.equal(all.find((entry) => entry.key === "sealed:packs").isParent, false);
  assert.equal(all.find((entry) => entry.key === "sealedMarket").isParent, true);
});

test("the chart model clips submarkets to the same backend window as parents", () => {
  const all = buildComparableSeries(overview, sealedSeries);
  const selected = all.filter((entry) => ["raw", "sealedMarket", "sealed:boosterBox"].includes(entry.key));
  const model = buildExplorerChartModel(overview, selected, "7D");
  assert.equal(model.available, true);
  assert.deepEqual(model.series.map((entry) => entry.key), ["raw", "sealedMarket", "sealed:boosterBox"]);
  // ONE date domain for every line, taken from the published window.
  assert.equal(model.startDate, "2024-01-01");
  assert.equal(model.endDate, "2024-01-05");
  for (const entry of model.series) {
    assert.equal(entry.values.length, model.dates.length, entry.key);
  }
  // A series with no available shared-comparison change draws no line.
  const unavailable = buildExplorerChartModel(overview, selected, "6M");
  assert.equal(unavailable.available, false);
});
