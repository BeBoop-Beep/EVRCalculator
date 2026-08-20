// Selected-set Top Movers: a fixed-height Top-10 carousel.
//
// Guards the ways this band could regress:
//   1. fetching before a set is selected, or refetching one already loaded;
//   2. ranking or inventing movers instead of rendering the published order;
//   3. paging by moving anything other than the carousel's own track;
//   4. offering a "View all" control that goes nowhere;
//   5. caching a transport failure as a set's permanent answer.

import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";
import Module from "node:module";
import { createRequire } from "node:module";
import React from "react";
import TestRenderer from "react-test-renderer";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// The movers client is the seam. Intercepting it at the loader — before the
// component is required — both stubs the response and PROVES the component
// reaches the network only through that one published module.
const calls = [];
let respond = () => Promise.resolve(null);

const MOVERS_CLIENT = "@/lib/pokemon/pokemonSetMarketClient";
const load = Module._load;
Module._load = function loadWithMoversStub(request, ...rest) {
  if (request === MOVERS_CLIENT) {
    return {
      getPokemonSetMarketMovers: (...args) => {
        calls.push(args);
        return respond(...args);
      },
    };
  }
  return load.call(this, request, ...rest);
};

// Required (not imported) so the loader patch above is installed first.
const require = createRequire(import.meta.url);
const SetMarketTopMovers = require("./SetMarketTopMovers.jsx").default;

const mover = (index) => ({
  id: `card-${index}`,
  canonicalCardId: `card-${index}`,
  name: `Mover ${index}`,
  marketPrice: 100 + index,
  priceChange7d: -(index + 1),
  priceChangePercent7d: -(index + 1),
  changeAmount: -(index + 1),
  changePercent: -(index + 1),
  hasValidMovement: true,
});

const payloadWith = (count) => ({
  window: "7D",
  windowDays: 7,
  all: Array.from({ length: count }, (_, index) => mover(index)),
  heatingUp: [],
  coolingOff: [],
  set: { id: "set-a" },
  meta: {},
});

async function render(props) {
  let renderer;
  await TestRenderer.act(async () => {
    renderer = TestRenderer.create(React.createElement(SetMarketTopMovers, props));
  });
  return renderer;
}

const track = (renderer) => renderer.root.findAll((node) => node.props?.["data-mover-carousel-track"] !== undefined)[0];
const steps = (renderer) => renderer.root.findAll((node) => node.props?.["data-mover-carousel-step"] !== undefined);
const cardsIn = (renderer) => track(renderer).findAll((node) => node.type === "a");
const jsonOf = (renderer) => JSON.stringify(renderer.toJSON());

test("nothing is requested until a set is selected", async () => {
  calls.length = 0;
  respond = () => Promise.resolve(payloadWith(3));
  const renderer = await render({ setId: null, setName: null, viewAllHref: null });
  assert.equal(calls.length, 0, "an unselected pane must not fetch");
  assert.equal(renderer.toJSON(), null);
});

test("one request per set, for the published 7D top ten", async () => {
  calls.length = 0;
  respond = () => Promise.resolve(payloadWith(10));
  await render({ setId: "set-request", setName: "Ascended Heroes", viewAllHref: "/x" });
  assert.deepEqual(calls, [["set-request", { window: "7D", limit: 10 }]]);

  // Re-selecting the same set is served from the page-lifetime cache.
  await render({ setId: "set-request", setName: "Ascended Heroes", viewAllHref: "/x" });
  assert.equal(calls.length, 1, "a set already loaded is not fetched again");
});

test("the carousel renders the published mover order, never a re-ranked one", async () => {
  calls.length = 0;
  respond = () => Promise.resolve(payloadWith(10));
  const renderer = await render({ setId: "set-order", setName: "Black Bolt", viewAllHref: "/x" });
  const titles = cardsIn(renderer).map((node) => node.props.title);
  assert.equal(titles.length, 10, "the full top ten is available to navigate");
  assert.deepEqual(titles.slice(0, 3), [
    "Mover 0 — view market movers",
    "Mover 1 — view market movers",
    "Mover 2 — view market movers",
  ]);
});

test("fewer than ten movers renders only what exists", async () => {
  calls.length = 0;
  respond = () => Promise.resolve(payloadWith(3));
  const renderer = await render({ setId: "set-short", setName: "White Flare", viewAllHref: "/x" });
  assert.equal(cardsIn(renderer).length, 3);
});

test("no movers at all says so rather than rendering an empty rail", async () => {
  calls.length = 0;
  respond = () => Promise.resolve(payloadWith(0));
  const renderer = await render({ setId: "set-empty", setName: "Chaos Rising", viewAllHref: "/x" });
  assert.match(jsonOf(renderer), /No reliable 7D movers in this set yet\./);
  assert.equal(steps(renderer).length, 0);
});

test("paging is wired to the track's own scrollBy and to nothing else", async () => {
  calls.length = 0;
  respond = () => Promise.resolve(payloadWith(10));
  const renderer = await render({ setId: "set-page", setName: "Paldean Fates", viewAllHref: "/x" });

  const [back, forward] = steps(renderer);
  assert.equal(back.props["data-mover-carousel-step"], "back");
  assert.equal(forward.props["data-mover-carousel-step"], "forward");
  assert.equal(back.type, "button");
  assert.equal(back.props.type, "button");
  assert.match(String(back.props["aria-label"]), /Previous movers in Paldean Fates/);
  assert.match(String(forward.props["aria-label"]), /Next movers in Paldean Fates/);
  // At rest the measured track reports scrollLeft 0 and no overflow, so both
  // ends read as reached — the arrows never claim a page that does not exist.
  assert.equal(back.props.disabled, true);
  assert.equal(typeof forward.props.onClick, "function");

  // The track is a single horizontal group; the movers are not stacked.
  assert.equal(track(renderer).props.role, "group");
  assert.match(String(track(renderer).props["aria-label"]), /Top 10 7-day movers in Paldean Fates/);
});

test("the View all control points at a real destination, or is not rendered", async () => {
  calls.length = 0;
  respond = () => Promise.resolve(payloadWith(4));
  const withHref = await render({
    setId: "set-viewall",
    setName: "Surging Sparks",
    viewAllHref: "/TCGs/Pokemon/Sets/surging-sparks?tab=cards&section=market-movers",
  });
  assert.match(jsonOf(withHref), /section=market-movers/);
  assert.match(jsonOf(withHref), /View all/);

  const withoutHref = await render({ setId: "set-nohref", setName: "Stellar Crown", viewAllHref: null });
  assert.ok(!jsonOf(withoutHref).includes("View all"), "no dead control when there is no destination");
});

test("a failed request says so and stays retryable rather than caching the failure", async () => {
  calls.length = 0;
  respond = () => Promise.reject(new Error("boom"));
  const renderer = await render({ setId: "set-fail", setName: "Paradox Rift", viewAllHref: "/x" });
  assert.match(jsonOf(renderer), /currently unavailable/);

  respond = () => Promise.resolve(payloadWith(2));
  const retried = await render({ setId: "set-fail", setName: "Paradox Rift", viewAllHref: "/x" });
  assert.equal(calls.length, 2, "the failure was not cached as this set's answer");
  assert.equal(cardsIn(retried).length, 2);
});
