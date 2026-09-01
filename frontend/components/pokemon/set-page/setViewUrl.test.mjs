import assert from "node:assert/strict";
import test from "node:test";
import { buildSameSetViewUrl, normalizeSetViewTab } from "./setViewUrl.mjs";

const build = (from, tab, section = null, extra = {}) => buildSameSetViewUrl({ pathname: "/TCGs/Pokemon/Sets/prismatic-evolutions", searchParams: new URLSearchParams(from), tab, section, extra });

test("primary Set transitions preserve the current URL semantics", () => {
  assert.equal(build("tab=overview", "market"), "/TCGs/Pokemon/Sets/prismatic-evolutions?tab=market");
  assert.equal(build("tab=market", "cards"), "/TCGs/Pokemon/Sets/prismatic-evolutions?tab=cards");
  assert.equal(build("tab=cards", "pull-rates"), "/TCGs/Pokemon/Sets/prismatic-evolutions?tab=pull-rates");
  assert.equal(build("tab=pull-rates", "rip"), "/TCGs/Pokemon/Sets/prismatic-evolutions?tab=overview");
  assert.equal(normalizeSetViewTab("analytics"), "overview");
});

test("Cards subsection transitions set and remove section exactly", () => {
  assert.equal(build("tab=cards", "cards", "market-movers"), "/TCGs/Pokemon/Sets/prismatic-evolutions?tab=cards&section=market-movers");
  assert.equal(build("tab=cards&section=market-movers", "cards", "all-cards"), "/TCGs/Pokemon/Sets/prismatic-evolutions?tab=cards&section=all-cards");
});

test("unrelated and existing control parameters are preserved while explicit extras apply", () => {
  assert.equal(build("tab=overview&sealedProduct=box&unknown=keep", "market"), "/TCGs/Pokemon/Sets/prismatic-evolutions?tab=market&sealedProduct=box&unknown=keep");
  assert.equal(build("tab=cards&movement=gainers&card_sort=name", "cards", "market-movers", { card_sort: "7d-movers", movement: "all" }), "/TCGs/Pokemon/Sets/prismatic-evolutions?tab=cards&movement=all&card_sort=7d-movers&section=market-movers");
  assert.equal(build("tab=cards&movement=all", "cards", null, { movement: null }), "/TCGs/Pokemon/Sets/prismatic-evolutions?tab=cards");
});

test("building the already-active view is stable", () => {
  const current = "tab=cards&section=market-movers&unknown=keep";
  assert.equal(build(current, "cards", "market-movers"), `/TCGs/Pokemon/Sets/prismatic-evolutions?${current}`);
});
