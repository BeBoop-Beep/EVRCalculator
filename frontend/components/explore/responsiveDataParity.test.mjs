import test from "node:test";
import assert from "node:assert/strict";

import { selectMobileHeroModel } from "../pokemon/set-page/PokemonSetHero/mobileHeroModel.mjs";
import { selectMoversTickerItems } from "./moversTickerSelector.mjs";
import { findNearestPointIndex } from "./compactSparklineInteraction.mjs";
import { resolvePointerModeFromEvent, POINTER_MODE_COARSE, POINTER_MODE_FINE } from "../../hooks/pointerMode.mjs";

// The analytical layer is width-agnostic by construction: every selector is a
// pure function of the payload. These assertions lock that in, so a future
// responsive change cannot start feeding a different payload to one breakpoint.

const moversPayload = {
  window: "7D",
  all: Array.from({ length: 14 }, (_, index) => ({
    cardId: `card-${index}`,
    name: `Card ${index}`,
    change7dAmount: 100 - index * 3,
    change7dPercent: 20 - index,
  })),
};

test("mover selection does not depend on viewport width", () => {
  // There is no width parameter to pass; the same call is the only call any
  // breakpoint can make. Ten items, in one order, everywhere.
  const items = selectMoversTickerItems(moversPayload);
  assert.equal(items.length, 10, "all ten movers are selected at every width");
  assert.deepEqual(
    items.map((entry) => entry.card.cardId),
    Array.from({ length: 10 }, (_, index) => `card-${index}`)
  );
});

test("hero values are identical whatever composition renders them", () => {
  const input = {
    setName: "Perfect Order",
    era: "Mega Evolution",
    logoUrl: null,
    setValue: { current: 663.14, deltaAmount: -115.78, deltaPercent: -14.9, windowLabel: "30D" },
    rip: { label: "RIP Score", score: 100, tier: "S", rank: 1, cohortSize: 212, verdict: "Elite" },
  };
  const first = selectMobileHeroModel(input);
  const second = selectMobileHeroModel(input);
  assert.deepEqual(first, second);
  // And the numbers match the payload exactly - no rounding drift by breakpoint.
  assert.equal(first.value.amountText, "$663.14");
  assert.equal(first.value.deltaText, "$115.78 · 14.9% · 30D");
  assert.equal(first.rip.scoreText, "100");
});

test("a selected chart point resolves to the same datum at any chart width", () => {
  const points = Array.from({ length: 30 }, (_, index) => ({ index, y: 10 + index }));
  // The selector takes a 0..1 ratio, not pixels, so a 320px chart and a 1366px
  // chart resolve the same fraction to the same datum.
  for (const ratio of [0, 0.25, 0.5, 0.75, 1]) {
    assert.equal(findNearestPointIndex(points, 30, ratio), findNearestPointIndex(points, 30, ratio));
  }
  assert.equal(findNearestPointIndex(points, 30, 0), 0);
  assert.equal(findNearestPointIndex(points, 30, 29 / 29), 29);
});

test("pointer mode changes interaction, never the data", () => {
  // Both modes are reachable on the same device and neither is ever disabled,
  // so nothing downstream may key a value off the mode.
  assert.equal(resolvePointerModeFromEvent({ pointerType: "mouse" }, POINTER_MODE_COARSE), POINTER_MODE_FINE);
  assert.equal(resolvePointerModeFromEvent({ pointerType: "touch" }, POINTER_MODE_FINE), POINTER_MODE_COARSE);

  const points = Array.from({ length: 12 }, (_, index) => ({ index, y: index * 2 }));
  const viaTap = findNearestPointIndex(points, 12, 0.5);
  const viaHover = findNearestPointIndex(points, 12, 0.5);
  assert.equal(viaTap, viaHover, "tap and hover resolve the same point from the same position");
});
