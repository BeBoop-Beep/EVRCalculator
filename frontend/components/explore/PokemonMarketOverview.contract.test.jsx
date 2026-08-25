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
      // THREE series, three different numbers, all true:
      //   changes       - the SHARED comparison domain (what the chart draws).
      //   familyChanges - this market's OWN history from its own tracking
      //                   start, which reaches further back and so differs.
      changes: { "1D": change(0.5), "7D": change(1.5), "30D": change(2.25), "6M": missing(), "1Y": missing(), SinceTracking: change(2.25) },
      familyChanges: { "1D": change(0.5), "7D": change(1.5), "30D": change(2.25), "6M": missing(), "1Y": missing(), SinceTracking: change(6.18) },
    },
    topChase: {
      basketValue: 4011.1,
      indexValue: 96.5,
      historyStartDate: "2024-01-01",
      trend: [["2024-01-01", 100], ["2024-01-04", 96.5]],
      // The tracked basket grew while price performance fell.
      basketChanges: { "1D": change(1.25), "7D": change(4.5), "30D": change(4.5), "6M": missing(), "1Y": missing(), SinceTracking: change(4.5) },
      changes: { "1D": change(-0.25), "7D": change(-1.75), "30D": change(-3.5), "6M": missing(), "1Y": missing(), SinceTracking: change(-3.5) },
      familyChanges: { "1D": change(-0.25), "7D": change(-1.75), "30D": change(-3.5), "6M": missing(), "1Y": missing(), SinceTracking: change(-8.4) },
    },
  },
};

// The period column is dynamic and CONTROLLED by PokemonMarketAnalysis, so
// every render here names the window under test. "All" is the default because
// it is the window where the two since-tracking series are most easily
// confused, which is exactly what most of these tests are guarding.
function render(overview, selectedWindow = "All", selectedLabel = "Since Tracking") {
  let renderer;
  TestRenderer.act(() => {
    renderer = TestRenderer.create(
      React.createElement(PokemonMarketOverview, { overview, selectedWindow, selectedLabel })
    );
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
  // Tracked Market Value spans value + since tracking; Price Performance spans
  // the index plus the one dynamic period column.
  assert.equal(groups[0].props.colSpan, 2);
  assert.equal(groups[1].props.colSpan, 2);
});

test("the Since Tracking column reads the family own history, not the shared span", () => {
  const renderer = render(overview);
  const rawRow = renderer.root.findAll((node) => node.props?.["data-market-overview-row"] === "raw")[0];

  const sinceTrackingCell = rawRow.findAll((node) => node.props?.["data-market-overview-tracked-change"] === "All")[0];
  const sharedCell = rawRow.findAll((node) => node.props?.["data-market-overview-change"] === "All")[0];

  // Since Tracking is +6.18%: the family's own tracking start, which is what
  // the 102.25 index level is measured against.
  assert.match(textOf(sinceTrackingCell), /\+6\.18%/);
  // The dynamic period column follows the chart, which is a cross-market
  // comparison, so it reports the SHARED +2.25%.
  assert.match(textOf(sharedCell), /\+2\.25%/);
  // Their equality was the defect; they must now be different statements.
  assert.notEqual(textOf(sinceTrackingCell), textOf(sharedCell));

  // Screen readers get the dimension spoken, not inferred from position.
  assert.match(textOf(sinceTrackingCell), /Raw Card Market, Price Performance, Since Tracking: up 6\.18 percent\./);
});

test("Since Tracking remains price performance when the tracked basket grew", () => {
  const renderer = render(overview);
  const chaseRow = renderer.root.findAll((node) => node.props?.["data-market-overview-row"] === "topChase")[0];
  const sinceTracking = chaseRow.findAll((node) => node.props?.["data-market-overview-tracked-change"] === "All")[0];
  const shared = chaseRow.findAll((node) => node.props?.["data-market-overview-change"] === "All")[0];
  // The tracked basket grew +4.50%, but neither column may report that number:
  // both are price performance. Since Tracking is the family own -8.40%.
  assert.match(textOf(sinceTracking), /−8\.40%/);
  assert.match(textOf(shared), /−3\.50%/);
  assert.doesNotMatch(textOf(sinceTracking), /4\.50%/);
});

test("the dynamic period column reports the backend percentage for the selected window", () => {
  // One window at a time, each read straight from `changes` — the column
  // heading and the figures move together and are never mixed.
  for (const [key, label, raw, chase] of [
    ["1D", "1D", /\+0\.50%/, /−0\.25%/],
    ["7D", "7D", /\+1\.50%/, /−1\.75%/],
    ["30D", "30D", /\+2\.25%/, /−3\.50%/],
  ]) {
    const renderer = render(overview, key, label);
    const heading = renderer.root.findAll((node) => node.props?.["data-market-overview-period-heading"] !== undefined)[0];
    assert.equal(textOf(heading), label);
    assert.equal(heading.props["data-market-overview-period-heading"], key);

    const rawRow = renderer.root.findAll((node) => node.props?.["data-market-overview-row"] === "raw")[0];
    const rawCell = rawRow.findAll((node) => node.props?.["data-market-overview-change"] === key)[0];
    assert.match(textOf(rawCell), raw);
    assert.match(textOf(rawCell), new RegExp(`Raw Card Market, Price Performance, ${label}:`));

    const chaseRow = renderer.root.findAll((node) => node.props?.["data-market-overview-row"] === "topChase")[0];
    assert.match(textOf(chaseRow.findAll((node) => node.props?.["data-market-overview-change"] === key)[0]), chase);
  }
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

test("mobile summary rows are accessible controls synchronized by family key", () => {
  const renderer = render(overview);
  const toggles = renderer.root.findAll((node) => node.props?.["data-market-overview-mobile-toggle"] !== undefined);
  assert.deepEqual(toggles.map((node) => node.props["data-market-overview-mobile-toggle"]), ["raw", "topChase"]);
  assert.ok(toggles.every((node) => node.type === "button"));
  assert.ok(toggles.every((node) => node.props["aria-pressed"] === true));
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
  // The since-tracking line is the FAMILY series (+6.18%), not the shared one.
  assert.match(trackedGroup, /\+6\.18%/);
  assert.match(trackedGroup, /since tracking/);

  const priceGroup = textOf(groups[1]);
  assert.match(priceGroup, /Market Index/);
  assert.match(priceGroup, /102\.25/);
  assert.match(priceGroup, /\+2\.25%/);

  const cardText = textOf(rawCard);
  assert.match(cardText, /Raw Card Market, Price Performance, Since Tracking: up 6\.18 percent\./);
});

test("the mobile card's period line follows the same shared selection", () => {
  // Same data model as desktop, compact presentation — never the five-column
  // table squeezed onto a 360px screen.
  const renderer = render(overview, "7D", "7D");
  const rawCard = renderer.root.findAll((node) => node.props?.["data-market-overview-card"] === "raw")[0];
  const periodLine = rawCard.findAll((node) => node.props?.["data-market-overview-change"] === "7D")[0];
  assert.match(textOf(periodLine), /\+1\.50%/);
  assert.match(textOf(periodLine), /7D/);
  assert.match(textOf(periodLine), /Raw Card Market, Price Performance, 7D: up 1\.50 percent\./);
  // The since-tracking line beside it is fixed to the family series and does
  // not follow the selection at all.
  const trackedLine = rawCard.findAll((node) => node.props?.["data-market-overview-tracked-change"] === "All")[0];
  assert.match(textOf(trackedLine), /\+6\.18%/);
  assert.match(textOf(trackedLine), /since tracking/);
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
  assert.match(joined, /current continuous tracking segment/i);
  assert.match(joined, /not a score/i);
  assert.match(joined, /base 100/i);
  assert.match(joined, /Chain-linking prevents newly added or removed constituents from creating an artificial jump/i);
  assert.match(joined, /after one enters, its later price movement affects the index/i);
  // The index level must be explained against its OWN base.
  assert.match(joined, /above its own index base/i);
});

test("a snapshot without basketChanges still shows the canonical Since Tracking return", () => {
  const legacy = resolveMarketOverview({
    marketOverview: {
      ...SNAPSHOT.marketOverview,
      raw: { ...SNAPSHOT.marketOverview.raw, basketChanges: undefined },
      topChase: { ...SNAPSHOT.marketOverview.topChase, basketChanges: undefined },
    },
  });
  const renderer = render(legacy);
  const rawRow = renderer.root.findAll((node) => node.props?.["data-market-overview-row"] === "raw")[0];
  assert.match(textOf(rawRow.findAll((node) => node.props?.["data-market-overview-tracked-change"] === "All")[0]), /\+6\.18%/);
  assert.match(textOf(rawRow.findAll((node) => node.props?.["data-market-overview-change"] === "All")[0]), /\+2\.25%/);
});

test("a snapshot published before familyChanges reports unavailable, never the shared number", () => {
  // The pre-split contract. Silently falling back to `changes` here is exactly
  // the lie this column was fixed to stop telling, so it shows a dash instead.
  const legacy = resolveMarketOverview({
    marketOverview: {
      ...SNAPSHOT.marketOverview,
      raw: { ...SNAPSHOT.marketOverview.raw, familyChanges: undefined },
      topChase: { ...SNAPSHOT.marketOverview.topChase, familyChanges: undefined },
    },
  });
  const renderer = render(legacy);
  const rawRow = renderer.root.findAll((node) => node.props?.["data-market-overview-row"] === "raw")[0];
  const cell = rawRow.findAll((node) => node.props?.["data-market-overview-tracked-change"] === "All")[0];
  assert.doesNotMatch(textOf(cell), /2\.25%/);
  assert.match(textOf(cell), /—/);
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
