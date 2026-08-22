import test from "node:test";
import assert from "node:assert/strict";
import React, { act } from "react";
import TestRenderer from "react-test-renderer";

import SetMarketMobileHero from "./SetMarketMobileHero.jsx";
import SetMarketMobileMovers from "./SetMarketMobileMovers.jsx";
import SetMarketMobileTopChase from "./SetMarketMobileTopChase.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// The chart-bearing sections (Set Value, Sealed) are covered by the source
// contract test instead: both mount Recharts through ChartFrame, which needs a
// real ResizeObserver and a measured box that react-test-renderer cannot give.
// Everything below renders without a chart.

async function render(element) {
  let renderer;
  await act(async () => {
    renderer = TestRenderer.create(element);
  });
  return renderer;
}

const textOf = (renderer) =>
  renderer.root
    .findAll((node) => typeof node.type === "string")
    .flatMap((node) => node.children)
    .filter((child) => typeof child === "string")
    .join(" ");

test("the hero prints identity plus only the metrics the set publishes", async () => {
  const renderer = await render(
    <SetMarketMobileHero
      id="set-detail-market-hero"
      setName="Pitch Black"
      era="Scarlet & Violet"
      logoUrl="https://images.example/logo.png"
      releaseDateText="Aug 1, 2025"
      totalCards={191}
      ripTier="S"
      ripRank={3}
      ripCohortSize={30}
    />
  );
  const text = textOf(renderer);
  assert.match(text, /Pitch Black/);
  assert.match(text, /Scarlet & Violet/);
  assert.match(text, /Aug 1, 2025/);
  assert.match(text, /191/);
  assert.match(text, /#3/);
  assert.match(text, /of 30/);
  assert.match(text, /S Tier/);
});

test("the hero drops metric cells rather than printing placeholders", async () => {
  const renderer = await render(<SetMarketMobileHero id="hero" setName="Unknown Set" />);
  assert.equal(renderer.root.findAll((node) => node.props?.["data-market-mobile-hero-metrics"]).length, 0);
  assert.doesNotMatch(textOf(renderer), /—|N\/A|\$0/);
});

test("the hero never renders a second set picker", async () => {
  const renderer = await render(<SetMarketMobileHero id="hero" setName="Pitch Black" />);
  assert.equal(renderer.root.findAllByType("button").length, 0);
  assert.equal(renderer.root.findAll((node) => node.props?.role === "listbox").length, 0);
});

test("movers render one tappable card per qualifying mover, fixed to 7D", async () => {
  const renderer = await render(
    <SetMarketMobileMovers
      id="set-detail-market-movers"
      entry={{
        all: [
          { id: "a", name: "Charizard ex", marketPrice: 412.5, change7dAmount: 22.4, change7dPercent: 5.7 },
          { id: "b", name: "Pikachu ex", marketPrice: 90, change7dAmount: -3.1, change7dPercent: -3.3 },
        ],
      }}
      viewAllHref="/pokemon?tab=cards&section=market-movers"
    />
  );
  const cards = renderer.root.findAll((node) => node.props?.["data-market-mobile-mover"]);
  assert.equal(cards.length, 2);
  const text = textOf(renderer);
  assert.match(text, /7D Market Movers/);
  assert.match(text, /Charizard ex/);
  assert.match(text, /\$412\.50/);
  assert.match(text, /\+\$22\.40/);
  assert.match(text, /−3\.3%/);
  // No timeframe control: this section is fixed to 7D by product definition.
  assert.equal(renderer.root.findAll((node) => node.props?.role === "radiogroup").length, 0);
});

test("movers degrade to a message instead of a broken rail", async () => {
  const renderer = await render(<SetMarketMobileMovers id="movers" entry={{ all: [] }} />);
  assert.equal(renderer.root.findAll((node) => node.props?.["data-market-mobile-movers-rail"]).length, 0);
  assert.match(textOf(renderer), /No reliable 7-day movers/);
});

const chaseCards = Array.from({ length: 9 }, (_, index) => ({
  id: `card-${index}`,
  name: `Chase ${index}`,
  rarity: "Special Illustration Rare",
  marketPrice: 500 - index * 30,
  deltas: { "30D": { amount: 5 - index, percent: 2 - index, startDate: "2026-07-20", endDate: "2026-08-19" } },
}));

test("top chase is one featured card above a compact ranked list", async () => {
  const renderer = await render(
    <SetMarketMobileTopChase
      id="set-detail-market-top-chase"
      cards={chaseCards}
      selectedWindowKey="30D"
      marketAsOfDate="2026-08-19"
      rowHref="/pokemon?tab=cards"
    />
  );
  const featured = renderer.root.findAll((node) => node.props?.["data-market-mobile-chase-featured"]);
  assert.equal(featured.length, 1, "exactly one featured card");
  // Preview shows #2-#5; the rest stay one tap away rather than being dropped.
  assert.equal(renderer.root.findAll((node) => node.props?.["data-market-mobile-chase-row"]).length, 4);

  const text = textOf(renderer);
  assert.match(text, /Top Chase Cards/);
  assert.match(text, /#1/);
  assert.match(text, /Chase 0/);
  assert.match(text, /\$500\.00/);
  assert.match(text, /Show 4 more/);

  await act(async () => {
    renderer.root
      .findAll((node) => node.type === "button" && node.props?.["aria-expanded"] === false)[0]
      .props.onClick();
  });
  assert.equal(renderer.root.findAll((node) => node.props?.["data-market-mobile-chase-row"]).length, 8);
});

test("top chase renders whatever exists when fewer than ten cards are priced", async () => {
  const renderer = await render(<SetMarketMobileTopChase id="chase" cards={chaseCards.slice(0, 2)} selectedWindowKey="30D" />);
  assert.equal(renderer.root.findAll((node) => node.props?.["data-market-mobile-chase-featured"]).length, 1);
  assert.equal(renderer.root.findAll((node) => node.props?.["data-market-mobile-chase-row"]).length, 1);
  assert.doesNotMatch(textOf(renderer), /Show \d+ more/);
});

test("top chase carries no per-row microcharts on mobile", async () => {
  const renderer = await render(<SetMarketMobileTopChase id="chase" cards={chaseCards} selectedWindowKey="30D" />);
  assert.equal(renderer.root.findAllByType("svg").filter((node) => node.props?.viewBox !== "0 0 20 20").length, 0);
});
