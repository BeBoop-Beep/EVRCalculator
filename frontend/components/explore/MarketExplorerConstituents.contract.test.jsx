// Current Constituents — the "what is inside this index" panel.
//
// The properties pinned here are the ones that make composition trustworthy:
// the columns follow the ASSET (a rarity column must never fill with product
// families), only ONE market is described at a time, a bounded preview says so
// rather than implying completeness, and a segment whose composition has not
// been published yet reports that instead of showing an empty table.

import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";

import MarketExplorerConstituents from "./MarketExplorerConstituents.jsx";
import {
  CONSTITUENTS_AVAILABLE,
  CONSTITUENTS_NOT_APPLICABLE,
  CONSTITUENTS_PENDING_PUBLICATION,
  PENDING_PUBLICATION_MESSAGE,
  resolveActiveDetailSeriesId,
  resolveSeriesConstituents,
} from "@/lib/explore/marketExplorerConstituents.mjs";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const cardRow = (index) => ({
  rank: index,
  canonicalCardId: `card-${index}`,
  cardName: `Charizard ex ${index}`,
  setName: "Ascended Heroes",
  rarity: "Special Illustration Rare",
  marketPrice: 1000 - index,
});

const productRow = (index) => ({
  rank: index,
  sealedProductId: `product-${index}`,
  productName: `Surging Sparks ETB ${index}`,
  setName: "Surging Sparks",
  productFamilyLabel: "Elite Trainer Box",
  marketPrice: 100 - index,
});

const cardQuery = (overrides = {}) => ({
  key: "query:cards-fp",
  label: "Global · SIR · Top 10",
  asset: "cards",
  available: true,
  asOf: "2026-08-25",
  spec: { asset: "cards", mode: "chase" },
  currentConstituents: Array.from({ length: 10 }, (_, index) => cardRow(index + 1)),
  reconciliation: { requestedTopN: 10, actualConstituentCount: 10, eligibleUniverseCount: 412 },
  ...overrides,
});

const sealedQuery = (overrides = {}) => ({
  key: "query:sealed-fp",
  label: "Global · Booster Boxes · Top 10",
  asset: "sealed",
  available: true,
  asOf: "2026-08-25",
  spec: { asset: "sealed", mode: "chase" },
  currentConstituents: Array.from({ length: 10 }, (_, index) => productRow(index + 1)),
  reconciliation: { requestedTopN: 10, actualConstituentCount: 10, eligibleUniverseCount: 88 },
  ...overrides,
});

function mount(props) {
  let renderer;
  act(() => {
    renderer = TestRenderer.create(<MarketExplorerConstituents {...props} />);
  });
  return renderer;
}

const panel = (renderer) =>
  renderer.root.find((node) => node.props?.["data-market-explorer-constituents"] !== undefined).props;
const rowIds = (renderer) =>
  [...new Set(renderer.root.findAll((node) => node.props?.["data-market-constituent"] !== undefined)
    .map((node) => node.props["data-market-constituent"]))];
const headers = (renderer) =>
  renderer.root.findAll((node) => node.type === "th").map((node) => node.props.children);
const text = (renderer) => JSON.stringify(renderer.toJSON());

// --- asset-specific shape ---------------------------------------------------

test("a card market shows card columns", () => {
  const renderer = mount({ selectedSeries: [cardQuery()], activeSeriesId: "query:cards-fp" });
  assert.equal(panel(renderer)["data-market-constituents-asset"], "cards");
  // Six columns now: the movement column trails the price and names the
  // window it is showing, so a "7D Change" header can never sit above 30D
  // numbers.
  assert.deepEqual(headers(renderer), ["Rank", "Card", "Set", "Rarity", "Price", "7D Change"]);
  assert.equal(rowIds(renderer).length, 10);
});

test("a sealed market shows product columns", () => {
  const renderer = mount({ selectedSeries: [sealedQuery()], activeSeriesId: "query:sealed-fp" });
  assert.equal(panel(renderer)["data-market-constituents-asset"], "sealed");
  assert.deepEqual(headers(renderer), ["Rank", "Product", "Set", "Family", "Price", "7D Change"]);
  assert.equal(rowIds(renderer).length, 10);
  assert.match(text(renderer), /Surging Sparks ETB 1/);
  assert.match(text(renderer), /Elite Trainer Box/);
});

test("row shapes are not forced together", () => {
  const cards = resolveSeriesConstituents(cardQuery());
  const sealed = resolveSeriesConstituents(sealedQuery());
  assert.equal(cards.idField, "canonicalCardId");
  assert.equal(sealed.idField, "sealedProductId");
  assert.ok(!("rarity" in sealed.rows[0]), "no fake rarity on a product");
  assert.ok(!("productFamilyLabel" in cards.rows[0]), "no fake family on a card");
});

// --- one active target ------------------------------------------------------

test("only one market is described at a time", () => {
  const renderer = mount({
    selectedSeries: [cardQuery(), sealedQuery()],
    activeSeriesId: "query:cards-fp",
  });
  assert.equal(rowIds(renderer).length, 10);
  assert.ok(rowIds(renderer).every((id) => id.startsWith("card-")));
  assert.equal(renderer.root.findAll((node) => node.type === "table").length, 1);
});

test("switching the target switches the asset with no stale cross-asset rows", () => {
  const selectedSeries = [cardQuery(), sealedQuery()];
  const cards = mount({ selectedSeries, activeSeriesId: "query:cards-fp" });
  assert.ok(rowIds(cards).every((id) => id.startsWith("card-")));

  const sealed = mount({ selectedSeries, activeSeriesId: "query:sealed-fp" });
  assert.equal(panel(sealed)["data-market-constituents-asset"], "sealed");
  assert.ok(rowIds(sealed).every((id) => id.startsWith("product-")));
  assert.ok(!text(sealed).includes("Charizard"), "no card may survive into a product table");
});

test("the picker offers every inspectable series and reports which is active", () => {
  const chosen = [];
  const renderer = mount({
    selectedSeries: [cardQuery(), sealedQuery()],
    activeSeriesId: "query:cards-fp",
    onSelectSeries: (id) => chosen.push(id),
  });
  const targets = renderer.root.findAll((node) => node.props?.["data-market-constituents-target"] !== undefined);
  assert.deepEqual(targets.map((node) => node.props["data-market-constituents-target"]),
    ["query:cards-fp", "query:sealed-fp"]);
  assert.equal(targets[0].props["aria-pressed"], true);
  assert.equal(targets[1].props["aria-pressed"], false);
  act(() => { targets[1].props.onClick(); });
  assert.deepEqual(chosen, ["query:sealed-fp"]);
});

test("the active target survives a new market being added", () => {
  const selected = [cardQuery(), sealedQuery()];
  assert.equal(resolveActiveDetailSeriesId(selected, "query:sealed-fp"), "query:sealed-fp");
  const grown = [...selected, cardQuery({ key: "query:another", label: "Another" })];
  assert.equal(resolveActiveDetailSeriesId(grown, "query:sealed-fp"), "query:sealed-fp",
    "adding a market must not yank the panel away from what is being read");
});

test("removing the inspected market falls back rather than pointing at nothing", () => {
  assert.equal(resolveActiveDetailSeriesId([cardQuery()], "query:sealed-fp"), "query:cards-fp");
  assert.equal(resolveActiveDetailSeriesId([], "query:sealed-fp"), null);
});

// --- bounding honesty -------------------------------------------------------

test("a Top 10 basket is complete and is not labelled a preview", () => {
  const model = resolveSeriesConstituents(cardQuery());
  assert.equal(model.availability, CONSTITUENTS_AVAILABLE);
  assert.equal(model.bounded, false);
  assert.equal(model.totalCount, 10);
  const renderer = mount({ selectedSeries: [cardQuery()], activeSeriesId: "query:cards-fp" });
  assert.equal(renderer.root.findAll((node) => node.props?.["data-market-constituents-bounded"] !== undefined).length, 0);
});

test("an All-mode market is previewed and says so with the true total", () => {
  const all = cardQuery({
    key: "query:all",
    spec: { asset: "cards", mode: "all" },
    currentConstituents: Array.from({ length: 400 }, (_, index) => cardRow(index + 1)),
    reconciliation: { requestedTopN: null, actualConstituentCount: 400, eligibleUniverseCount: 4127 },
  });
  const model = resolveSeriesConstituents(all);
  assert.equal(model.bounded, true);
  assert.equal(model.totalCount, 4127, "the true universe size, not the preview length");
  assert.equal(model.rows.length, 25);

  const renderer = mount({ selectedSeries: [all], activeSeriesId: "query:all" });
  const note = renderer.root.find((node) => node.props?.["data-market-constituents-bounded"] !== undefined);
  assert.match(JSON.stringify(note.props.children), /not the complete list/);
  assert.equal(rowIds(renderer).length, 25, "thousands of DOM rows are never rendered");
});

test("an All-mode preview is the most valuable constituents, price descending", () => {
  const model = resolveSeriesConstituents(cardQuery({
    spec: { asset: "cards", mode: "all" },
    currentConstituents: [cardRow(9), cardRow(1), cardRow(5)],
    reconciliation: { actualConstituentCount: 3, eligibleUniverseCount: 3 },
  }));
  assert.deepEqual(model.rows.map((row) => row.canonicalCardId), ["card-1", "card-5", "card-9"]);
});

test("a short basket is reported at its real size, never padded", () => {
  const short = sealedQuery({
    currentConstituents: Array.from({ length: 7 }, (_, index) => productRow(index + 1)),
    reconciliation: { requestedTopN: 10, actualConstituentCount: 7, eligibleUniverseCount: 7, belowRequestedTopN: true },
  });
  const renderer = mount({ selectedSeries: [short], activeSeriesId: "query:sealed-fp" });
  assert.equal(rowIds(renderer).length, 7);
  const note = renderer.root.find((node) => node.props?.["data-market-constituents-short"] !== undefined);
  assert.match(JSON.stringify(note.props.children), /fewer than the/);
});

// --- prepared quick segments ------------------------------------------------

test("a prepared segment's published roster is rendered", () => {
  const prepared = {
    key: "sealed:eliteTrainerBox",
    label: "Elite Trainer Boxes",
    available: true,
    group: "sealed",
    currentConstituents: {
      asOf: "2026-08-25",
      totalCount: 3,
      isComplete: true,
      idField: "sealedProductId",
      topConstituents: [productRow(1), productRow(2), productRow(3)],
    },
  };
  const model = resolveSeriesConstituents(prepared);
  assert.equal(model.availability, CONSTITUENTS_AVAILABLE);
  assert.equal(model.asset, "sealed");
  assert.equal(model.source, "prepared");
  assert.equal(model.bounded, false);
  const renderer = mount({ selectedSeries: [prepared], activeSeriesId: "sealed:eliteTrainerBox" });
  assert.equal(rowIds(renderer).length, 3);
});

test("a bounded prepared card preview is trusted from isComplete, not from length", () => {
  const prepared = {
    key: "card:raw:specialIllustrationRare",
    label: "SIR",
    available: true,
    group: "card",
    currentConstituents: {
      asOf: "2026-08-25",
      totalCount: 1200,
      isComplete: false,
      idField: "canonicalCardId",
      topConstituents: Array.from({ length: 25 }, (_, index) => cardRow(index + 1)),
    },
  };
  const model = resolveSeriesConstituents(prepared);
  assert.equal(model.bounded, true);
  assert.equal(model.totalCount, 1200);
});

test("a segment published before the contract reports pending publication", () => {
  const legacy = {
    key: "card:raw:illustrationRare",
    label: "Illustration Rare",
    available: true,
    group: "card",
    currentConstituents: null,
  };
  const model = resolveSeriesConstituents(legacy);
  assert.equal(model.availability, CONSTITUENTS_PENDING_PUBLICATION);

  const renderer = mount({ selectedSeries: [legacy], activeSeriesId: "card:raw:illustrationRare" });
  const note = renderer.root.find(
    (node) => node.props?.["data-market-constituents-unavailable"] !== undefined
  );
  assert.equal(note.props["data-market-constituents-unavailable"], CONSTITUENTS_PENDING_PUBLICATION);
  assert.match(JSON.stringify(note.props.children), /after the next market publication/);
  assert.equal(PENDING_PUBLICATION_MESSAGE.includes("next market publication"), true);
  assert.equal(renderer.root.findAll((node) => node.type === "table").length, 0,
    "an empty table would read as an empty market");
});

test("analytics still render for a segment with no published composition", () => {
  // The panel must not crash or blank the series; it reports only that the
  // COMPOSITION is pending.
  const legacy = { key: "card:raw:ultraRare", label: "Ultra Rare", available: true, group: "card", indexValue: 118.2 };
  const renderer = mount({ selectedSeries: [legacy], activeSeriesId: "card:raw:ultraRare" });
  assert.equal(panel(renderer)["data-market-constituents-availability"], CONSTITUENTS_PENDING_PUBLICATION);
  assert.match(text(renderer), /Ultra Rare/);
});

// --- parent markets ---------------------------------------------------------

test("a parent market is not offered for enumeration", () => {
  const parent = { key: "raw", label: "Raw Card Market", available: true, isParent: true };
  const model = resolveSeriesConstituents(parent);
  assert.equal(model.availability, CONSTITUENTS_NOT_APPLICABLE);
  const renderer = mount({ selectedSeries: [parent, cardQuery()], activeSeriesId: "query:cards-fp" });
  const targets = renderer.root.findAll((node) => node.props?.["data-market-constituents-target"] !== undefined);
  assert.ok(!targets.some((node) => node.props["data-market-constituents-target"] === "raw"),
    "the whole tracked card universe is not a table");
});

test("nothing selected is stated rather than rendered as an empty market", () => {
  const renderer = mount({ selectedSeries: [], activeSeriesId: null });
  assert.equal(panel(renderer)["data-market-constituents-availability"], CONSTITUENTS_NOT_APPLICABLE);
  assert.equal(renderer.root.findAll((node) => node.type === "table").length, 0);
});

// --- mobile -----------------------------------------------------------------

test("mobile keeps set and price identity in a stacked row", () => {
  const renderer = mount({ selectedSeries: [sealedQuery()], activeSeriesId: "query:sealed-fp" });
  const cards = renderer.root.find((node) => node.props?.["data-market-constituents-cards"] !== undefined);
  assert.match(cards.props.className, /desk:hidden/);
  const rendered = text(renderer);
  assert.match(rendered, /Surging Sparks/, "set identity is never dropped on mobile");
  assert.match(rendered, /\$99\.00|\$99/, "nor is price");
});

test("the table scrolls inside its own container, never the page", () => {
  const renderer = mount({ selectedSeries: [cardQuery()], activeSeriesId: "query:cards-fp" });
  const table = renderer.root.find((node) => node.props?.["data-market-constituents-table"] !== undefined);
  assert.match(table.props.className, /overflow-x-auto/);
  assert.match(table.props.className, /hidden/);
});

// --- constituent movement ---------------------------------------------------
//
// The requirement: the table must answer BOTH "what is inside this market" and
// "how are those things moving". The failure modes it must not have are the
// aggregate-per-row lie and the zero-for-missing lie.

const movingRow = (index, percents) => ({
  ...cardRow(index),
  // A bare number per window; null where there is no comparable observation.
  changes: { ...percents },
});

const movingQuery = () => cardQuery({
  currentConstituents: [
    movingRow(1, { "1D": 0.4, "7D": 4.8, "30D": -12.5, "3M": null }),
    movingRow(2, { "1D": -0.1, "7D": -2.1, "30D": 3.3, "3M": 0 }),
  ],
  reconciliation: { requestedTopN: 10, actualConstituentCount: 2, eligibleUniverseCount: 2 },
});

const windowButtons = (renderer) =>
  renderer.root.findAll((node) => node.props?.["data-market-constituents-window"] !== undefined);

/** The rendered percentage strings, read off the tree rather than the props. */
const changeValues = (renderer) => {
  const found = [];
  const walk = (node) => {
    if (!node || typeof node !== "object") return;
    if (Array.isArray(node)) return node.forEach(walk);
    for (const match of String(JSON.stringify(node.children ?? "")).matchAll(/[+-]?\d+\.\d\d%/g)) {
      found.push(match[0]);
    }
    if (node.children) walk(node.children);
  };
  walk(renderer.toJSON());
  return found;
};

test("there is ONE movement column behind a local window control, not four", () => {
  const renderer = mount({ selectedSeries: [movingQuery()], activeSeriesId: "query:cards-fp" });
  const changeHeaders = headers(renderer).filter((label) => String(label).includes("Change"));
  assert.equal(changeHeaders.length, 1, "four simultaneous change columns overflow the table");
  const windows = windowButtons(renderer).map((node) => node.props["data-market-constituents-window"]);
  assert.deepEqual([...new Set(windows)], ["1D", "7D", "30D", "3M"]);
});

test("7D is the default window", () => {
  const renderer = mount({ selectedSeries: [movingQuery()], activeSeriesId: "query:cards-fp" });
  assert.equal(panel(renderer)["data-market-constituents-movement-window"], "7D");
  const active = windowButtons(renderer)
    .filter((node) => node.props["data-market-constituents-window-active"] === "true")
    .map((node) => node.props["data-market-constituents-window"]);
  assert.deepEqual([...new Set(active)], ["7D"]);
});

test("changing the window changes the column header AND the numbers", () => {
  const renderer = mount({ selectedSeries: [movingQuery()], activeSeriesId: "query:cards-fp" });
  assert.ok(headers(renderer).includes("7D Change"));
  assert.match(text(renderer), /\+4\.80%/);

  const thirtyDay = windowButtons(renderer)
    .find((node) => node.props["data-market-constituents-window"] === "30D");
  act(() => { thirtyDay.props.onClick(); });

  assert.ok(headers(renderer).includes("30D Change"));
  assert.ok(!headers(renderer).includes("7D Change"), "the header must follow the control");
  assert.match(text(renderer), /-12\.50%/);
  assert.ok(!/\+4\.80%/.test(text(renderer)), "the previous window's numbers must be gone");
});

test("each row moves on its own — the aggregate is never repeated down the column", () => {
  const renderer = mount({ selectedSeries: [movingQuery()], activeSeriesId: "query:cards-fp" });
  const values = changeValues(renderer);
  assert.ok(values.length >= 2, "both constituents must print a movement");
  assert.equal(new Set(values).size > 1, true, "two constituents must not print the same number");
});

test("no comparable history prints a dash, never 0.00%", () => {
  const renderer = mount({ selectedSeries: [movingQuery()], activeSeriesId: "query:cards-fp" });
  const threeMonth = windowButtons(renderer)
    .find((node) => node.props["data-market-constituents-window"] === "3M");
  act(() => { threeMonth.props.onClick(); });

  const unavailable = renderer.root.findAll(
    (node) => node.props?.["data-market-constituent-change-unavailable"] !== undefined
  );
  assert.ok(unavailable.length > 0, "a constituent with no 3M baseline must show a dash");
  // ...and a genuine zero is still printed as a zero, because the price really
  // did not move. The two must never collapse into one presentation.
  assert.match(text(renderer), /0\.00%/);
});

test("a market published before the movement contract says so once, not per row", () => {
  const renderer = mount({ selectedSeries: [cardQuery()], activeSeriesId: "query:cards-fp" });
  assert.equal(panel(renderer)["data-market-constituents-has-movement"], "false");
  const notice = renderer.root.findAll(
    (node) => node.props?.["data-market-constituents-movement-pending"] !== undefined
  );
  assert.equal(notice.length, 1);
});

test("mobile keeps price AND movement rather than compressing the desktop table", () => {
  const renderer = mount({ selectedSeries: [movingQuery()], activeSeriesId: "query:cards-fp" });
  const cards = renderer.root.findAll(
    (node) => node.props?.["data-market-constituents-cards"] !== undefined
  );
  assert.equal(cards.length, 1, "one stacked list, not a squeezed table");
  const rendered = text(renderer);
  assert.match(rendered, /Ascended Heroes/, "set identity survives");
  assert.match(rendered, /\+4\.80%/, "movement survives");
});

test("a parent that publishes its roster CAN be inspected", () => {
  // Total Sealed is a parent AND publishes `currentConstituents`. It is the
  // only surface that lists the residual products belonging to no child
  // market, so excluding every parent from the picker made that roster
  // unreachable while the resolver was still willing to target it.
  const totalSealed = {
    key: "sealedMarket",
    label: "Sealed Market",
    isParent: true,
    available: true,
    currentConstituents: {
      idField: "sealedProductId",
      totalCount: 1,
      isComplete: true,
      asOf: "2026-08-25",
      topConstituents: [productRow(1)],
    },
  };
  const renderer = mount({ selectedSeries: [totalSealed], activeSeriesId: "sealedMarket" });
  assert.equal(panel(renderer)["data-market-constituents-availability"], CONSTITUENTS_AVAILABLE);
  assert.equal(panel(renderer)["data-market-constituents-asset"], "sealed");
  assert.match(text(renderer), /Surging Sparks ETB 1/);
});

test("a parent with NO published roster still reports the parent-market reason", () => {
  const rawParent = { key: "raw", label: "Raw Card Market", isParent: true, available: true };
  const renderer = mount({ selectedSeries: [rawParent], activeSeriesId: "raw" });
  assert.equal(panel(renderer)["data-market-constituents-availability"], CONSTITUENTS_NOT_APPLICABLE);
});
