// Market Overview, tested by RENDERING it against a snapshot fixture.
//
// Every displayed figure must trace to `marketOverview`. The two published
// dimensions — Tracked Market Value (`basketChanges`) and Price Performance
// (`changes`) — must render as separate, separately labeled column groups that
// read different data, and mobile must get a stacked-card composition rather
// than a table pushed into overflow.

import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer from "react-test-renderer";

import PokemonMarketOverview from "./PokemonMarketOverview.jsx";
import { resolveMarketOverview } from "@/lib/explore/marketOverviewPresentation.mjs";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const change = (percent) => ({ available: true, percent, startDate: "2024-01-01", endDate: "2024-01-04", coverage: "full" });
const missing = () => ({ available: false, percent: null, startDate: null, endDate: "2024-01-04", coverage: "unavailable" });

const SNAPSHOT = {
  marketOverview: {
    contractVersion: "pokemon-market-overview-v1",
    marketDate: "2024-01-04",
    coverage: { eligibleSetCount: 3, rawCardCount: 512, chaseCardCount: 30 },
    raw: {
      basketValue: 8123.45,
      indexValue: 102.25,
      historyStartDate: "2024-01-01",
      trend: [["2024-01-01", 100], ["2024-01-04", 102.25]],
      // Tracked Value grew far more than price performance — a set joined the
      // tracked universe. Nothing in the UI may treat these as one number.
      basketChanges: { "1D": change(3.5), "7D": change(9.75), "30D": change(9.75), "6M": missing(), "1Y": missing(), SinceTracking: change(9.75) },
      changes: { "1D": change(0.5), "7D": change(1.5), "30D": change(2.25), "6M": missing(), "1Y": missing(), SinceTracking: change(2.25) },
    },
    topChase: {
      basketValue: 4011.1,
      indexValue: 96.5,
      historyStartDate: "2024-01-01",
      trend: [["2024-01-01", 100], ["2024-01-04", 96.5]],
      // The tracked basket grew while price performance fell.
      basketChanges: { "1D": change(1.25), "7D": change(4.5), "30D": change(4.5), "6M": missing(), "1Y": missing(), SinceTracking: change(4.5) },
      changes: { "1D": change(-0.25), "7D": change(-1.75), "30D": change(-3.5), "6M": missing(), "1Y": missing(), SinceTracking: change(-3.5) },
    },
  },
};

function render(overview) {
  let renderer;
  TestRenderer.act(() => {
    renderer = TestRenderer.create(React.createElement(PokemonMarketOverview, { overview }));
  });
  return renderer;
}

// Walks the RENDERED instance tree (not the element tree), so text produced by
// nested components — the change cells, the popovers — is collected too.
function textOf(node) {
  if (node === null || node === undefined || node === false) return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  return (node.children || []).map(textOf).filter(Boolean).join(" ");
}

const overview = resolveMarketOverview(SNAPSHOT);

test("both markets render from the snapshot, in the locked order and copy", () => {
  const renderer = render(overview);
  const rows = renderer.root.findAll((node) => node.props?.["data-market-overview-row"] !== undefined);
  assert.deepEqual(rows.map((node) => node.props["data-market-overview-row"]), ["raw", "topChase"]);
  assert.match(textOf(rows[0]), /Raw Card Market/);
  assert.match(textOf(rows[1]), /Top 10 Chase Market/);

  const heading = renderer.root.findAll((node) => node.props?.id === "market-overview-heading")[0];
  assert.equal(textOf(heading), "Market Overview");
});

test("Tracked Value and Market Index are distinct, separately labeled concepts", () => {
  const renderer = render(overview);
  const tracked = renderer.root.findAll((node) => node.props?.["data-market-overview-metric"] === "trackedValue");
  const indexes = renderer.root.findAll((node) => node.props?.["data-market-overview-metric"] === "index");
  // One of each per market, per composition (desktop table + mobile cards).
  assert.equal(tracked.length, 4);
  assert.equal(indexes.length, 4);
  assert.equal(textOf(tracked[0]), "$8,123.45");
  assert.equal(textOf(indexes[0]), "102.25");
  assert.equal(textOf(tracked[1]), "$4,011.10");
  assert.equal(textOf(indexes[1]), "96.50");

  const all = textOf(renderer.root);
  assert.match(all, /Tracked Value/);
  assert.match(all, /Market Index/);
  // The dollar total is never labeled as a capitalization or a score.
  assert.doesNotMatch(all, /Basket Value/);
});

test("the desktop table groups the two dimensions with real colgroup headers", () => {
  const renderer = render(overview);
  const groups = renderer.root.findAll((node) => node.props?.["data-market-overview-group"] !== undefined && node.type === "th");
  assert.deepEqual(groups.map((node) => node.props["data-market-overview-group"]), ["trackedValue", "pricePerformance"]);
  assert.equal(textOf(groups[0]), "Tracked Market Value");
  assert.equal(textOf(groups[1]), "Price Performance");
  for (const group of groups) {
    assert.equal(group.props.scope, "colgroup");
    assert.ok(group.props.colSpan >= 2, "each group must actually span its columns");
  }
  // Tracked Market Value spans value + since; Price Performance spans the
  // index plus its four windows.
  assert.equal(groups[0].props.colSpan, 2);
  assert.equal(groups[1].props.colSpan, 5);
});

test("Tracked Value Since Tracking and Price Performance Since Tracking are different data", () => {
  const renderer = render(overview);
  const rawRow = renderer.root.findAll((node) => node.props?.["data-market-overview-row"] === "raw")[0];

  const trackedCell = rawRow.findAll((node) => node.props?.["data-market-overview-tracked-change"] === "All")[0];
  const priceCell = rawRow.findAll((node) => node.props?.["data-market-overview-change"] === "All")[0];

  // basketChanges.SinceTracking = +9.75%, changes.SinceTracking = +2.25%.
  assert.match(textOf(trackedCell), /\+9\.75%/);
  assert.match(textOf(priceCell), /\+2\.25%/);
  assert.notEqual(textOf(trackedCell), textOf(priceCell));

  // Screen readers get the dimension spoken, not inferred from position.
  assert.match(textOf(trackedCell), /Raw Card Market, Tracked Value, Since Tracking: up 9\.75 percent\./);
  assert.match(textOf(priceCell), /Raw Card Market, Price Performance, Since Tracking: up 2\.25 percent\./);
});

test("the tracked basket can grow while price performance falls", () => {
  const renderer = render(overview);
  const chaseRow = renderer.root.findAll((node) => node.props?.["data-market-overview-row"] === "topChase")[0];
  const tracked = chaseRow.findAll((node) => node.props?.["data-market-overview-tracked-change"] === "All")[0];
  const price = chaseRow.findAll((node) => node.props?.["data-market-overview-change"] === "All")[0];
  assert.match(textOf(tracked), /\+4\.50%/);
  assert.match(textOf(price), /−3\.50%/);
});

test("the price-performance cells report the backend percentages with a spoken direction", () => {
  const renderer = render(overview);
  const rawRow = renderer.root.findAll((node) => node.props?.["data-market-overview-row"] === "raw")[0];
  const rawText = textOf(rawRow);
  assert.match(rawText, /\+0\.50%/);
  assert.match(rawText, /\+1\.50%/);
  assert.match(rawText, /\+2\.25%/);
  assert.match(rawText, /Raw Card Market, Price Performance, 30D: up 2\.25 percent\./);

  const chaseRow = renderer.root.findAll((node) => node.props?.["data-market-overview-row"] === "topChase")[0];
  assert.match(textOf(chaseRow), /−3\.50%/);
  assert.match(textOf(chaseRow), /Top 10 Chase Market, Price Performance, Since Tracking: down 3\.50 percent\./);
});

test("mobile gets a stacked-card composition, not a horizontally scrolled table", () => {
  const renderer = render(overview);
  const cards = renderer.root.findAll((node) => node.props?.["data-market-overview-card"] !== undefined);
  assert.deepEqual(cards.map((node) => node.props["data-market-overview-card"]), ["raw", "topChase"]);

  const cardList = renderer.root.findAll((node) => node.props?.["data-market-overview-cards"] !== undefined)[0];
  assert.equal(cardList.type, "ul");
  assert.match(String(cardList.props.className), /desk:hidden/);
  assert.equal(cardList.findAll((node) => node.type === "table").length, 0);

  const table = renderer.root.findAll((node) => node.props?.["data-market-overview-table"] !== undefined)[0];
  assert.match(String(table.props.className), /hidden desk:block/);
  assert.doesNotMatch(String(table.props.className), /overflow-x/);
});

test("each mobile card explains BOTH dimensions on its own", () => {
  const renderer = render(overview);
  const rawCard = renderer.root.findAll((node) => node.props?.["data-market-overview-card"] === "raw")[0];

  // The card carries both labelled groups...
  const groups = rawCard.findAll((node) => node.props?.["data-market-overview-group"] !== undefined);
  assert.deepEqual(groups.map((node) => node.props["data-market-overview-group"]), ["trackedValue", "pricePerformance"]);

  const trackedGroup = textOf(groups[0]);
  assert.match(trackedGroup, /Tracked Value/);
  assert.match(trackedGroup, /\$8,123\.45/);
  assert.match(trackedGroup, /\+9\.75%/);
  assert.match(trackedGroup, /since tracking/);

  const priceGroup = textOf(groups[1]);
  assert.match(priceGroup, /Market Index/);
  assert.match(priceGroup, /102\.25/);
  assert.match(priceGroup, /\+2\.25%/);
  assert.match(priceGroup, /price performance/);

  // ...plus the short-window price-performance line.
  const cardText = textOf(rawCard);
  for (const window of ["1D", "7D", "30D"]) {
    assert.ok(cardText.includes(window), `mobile card must report ${window}`);
  }
  assert.match(cardText, /Raw Card Market, Price Performance, 30D: up 2\.25 percent\./);
  assert.match(cardText, /Raw Card Market, Tracked Value, Since Tracking: up 9\.75 percent\./);
});

// InfoPopover renders its body only while open, so the help copy is asserted
// where it actually lives in a closed popover: the text handed to the trigger.
function helpCopyOf(renderer) {
  return renderer.root
    .findAll((node) => typeof node.type === "function" && typeof node.props?.text === "string" && node.props.learnMoreHref === undefined)
    .map((node) => node.props.text);
}

test("no user-facing copy calls the tracked basket a market capitalization", () => {
  const renderer = render(overview);
  const copy = [textOf(renderer.root), ...helpCopyOf(renderer)].join(" ");
  // The only permitted occurrence is the explicit disclaimer inside help copy.
  assert.ok(copy.includes("This is not market capitalization."));
  assert.doesNotMatch(copy.replace(/This is not market capitalization\./g, ""), /market cap/i);
  assert.doesNotMatch(copy, /total Pok[eé]mon market value/i);
  assert.doesNotMatch(copy, /\b(bullish|bearish|overvalued|undervalued)\b/i);
});

test("the help copy explains the tracked universe and disclaims the index as a score", () => {
  const copy = helpCopyOf(render(overview));
  assert.ok(copy.length >= 3, `expected Tracked Value, Tracked Value change and Index help; got ${copy.length}`);
  const joined = copy.join(" ");
  assert.match(joined, /sets enter or leave the tracked universe/i);
  assert.match(joined, /intentionally includes the effect of sets entering or leaving tracking/i);
  assert.match(joined, /not a score/i);
  assert.match(joined, /base 100/i);
  assert.match(joined, /Chain-linking prevents newly added or removed sets from creating an artificial jump/i);
  assert.match(joined, /after a set enters, its later price movement affects the index/i);
});

test("a snapshot published before the extension shows no tracked-value percentage", () => {
  const legacy = resolveMarketOverview({
    marketOverview: {
      ...SNAPSHOT.marketOverview,
      raw: { ...SNAPSHOT.marketOverview.raw, basketChanges: undefined },
      topChase: { ...SNAPSHOT.marketOverview.topChase, basketChanges: undefined },
    },
  });
  const renderer = render(legacy);
  const rawRow = renderer.root.findAll((node) => node.props?.["data-market-overview-row"] === "raw")[0];
  const trackedCell = rawRow.findAll((node) => node.props?.["data-market-overview-tracked-change"] === "All")[0];
  // A dash and a spoken "not enough history" — never a locally derived figure.
  assert.match(textOf(trackedCell), /—/);
  assert.match(textOf(trackedCell), /not enough history/);
  // Price performance is unaffected.
  assert.match(textOf(rawRow.findAll((node) => node.props?.["data-market-overview-change"] === "All")[0]), /\+2\.25%/);
});

test("a missing overview degrades to a quiet unavailable state, not a crash", () => {
  for (const value of [null, undefined, { families: [] }]) {
    const renderer = render(value);
    const text = textOf(renderer.root);
    assert.match(text, /Market Overview/);
    assert.match(text, /temporarily unavailable/);
    assert.equal(renderer.root.findAll((node) => node.props?.["data-market-overview-row"] !== undefined).length, 0);
  }
});
