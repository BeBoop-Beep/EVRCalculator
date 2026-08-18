// Market Overview, tested by RENDERING it against a snapshot fixture.
//
// Every displayed figure must trace to `marketOverview`, Basket Value and
// Index must read as two clearly labeled concepts, and mobile must get a
// stacked-card composition rather than a table pushed into overflow.

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
      changes: { "1D": change(0.5), "7D": change(1.5), "30D": change(2.25), "6M": missing(), "1Y": missing(), SinceTracking: change(2.25) },
    },
    topChase: {
      basketValue: 4011.1,
      indexValue: 96.5,
      historyStartDate: "2024-01-01",
      trend: [["2024-01-01", 100], ["2024-01-04", 96.5]],
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

test("basket value and index are two distinct, separately labeled values", () => {
  const renderer = render(overview);
  const baskets = renderer.root.findAll((node) => node.props?.["data-market-overview-metric"] === "basketValue");
  const indexes = renderer.root.findAll((node) => node.props?.["data-market-overview-metric"] === "index");
  // One of each per market, per composition (desktop table + mobile cards).
  assert.equal(baskets.length, 4);
  assert.equal(indexes.length, 4);
  assert.equal(textOf(baskets[0]), "$8,123.45");
  assert.equal(textOf(indexes[0]), "102.25");
  assert.equal(textOf(baskets[1]), "$4,011.10");
  assert.equal(textOf(indexes[1]), "96.50");

  const all = textOf(renderer.root);
  assert.match(all, /Basket Value/);
  assert.match(all, /Market Index|Index/);
});

test("the change cells report the backend percentages with a spoken direction", () => {
  const renderer = render(overview);
  const rawRow = renderer.root.findAll((node) => node.props?.["data-market-overview-row"] === "raw")[0];
  const rawText = textOf(rawRow);
  assert.match(rawText, /\+0\.50%/);
  assert.match(rawText, /\+1\.50%/);
  assert.match(rawText, /\+2\.25%/);
  assert.match(rawText, /Raw Card Market, 30D: up 2\.25 percent\./);

  const chaseRow = renderer.root.findAll((node) => node.props?.["data-market-overview-row"] === "topChase")[0];
  assert.match(textOf(chaseRow), /−3\.50%/);
  assert.match(textOf(chaseRow), /Top 10 Chase Market, Since Tracking: down 3\.50 percent\./);
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

  // Each mobile card answers value, index and recent direction on its own.
  const rawCard = textOf(cards[0]);
  assert.match(rawCard, /\$8,123\.45/);
  assert.match(rawCard, /Basket Value/);
  assert.match(rawCard, /102\.25/);
  assert.match(rawCard, /Market Index/);
  assert.match(rawCard, /30D/);
  assert.match(rawCard, /Since Tracking/);
  assert.match(rawCard, /1D/);
  assert.match(rawCard, /7D/);
});

test("no user-facing copy calls the basket a market capitalization", () => {
  const rendered = textOf(render(overview).root).replace(/This is not market capitalization\./g, "");
  assert.doesNotMatch(rendered, /market cap/i);
  assert.doesNotMatch(rendered, /total Pok[eé]mon market value/i);
  assert.doesNotMatch(rendered, /\b(bullish|bearish|overvalued|undervalued|buy|sell)\b/i);
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
