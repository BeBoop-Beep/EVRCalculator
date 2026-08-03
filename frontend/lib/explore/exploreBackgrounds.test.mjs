import assert from "node:assert/strict";
import test from "node:test";

import { getExploreBackground } from "./exploreBackgrounds.mjs";

test("Pokémon Explore resolves to the approved local category artwork", () => {
  assert.equal(getExploreBackground("pokemon"), "/images/explore/pokemon-wordmark.svg");
  assert.equal(getExploreBackground(" Pokemon "), "/images/explore/pokemon-wordmark.svg");
});

test("unknown and future TCG categories fail safely without artwork", () => {
  assert.equal(getExploreBackground("onePiece"), null);
  assert.equal(getExploreBackground("lorcana"), null);
  assert.equal(getExploreBackground("all"), null);
  assert.equal(getExploreBackground(null), null);
});
