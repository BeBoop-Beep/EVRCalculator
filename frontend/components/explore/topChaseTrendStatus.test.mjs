import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

import { STANDARD_DELTA_WINDOW_KEYS } from "../../lib/explore/marketDeltaWindows.mjs";
import { selectTopChaseCards } from "../pokemon/set-page/Overview/topChaseCardsSelector.mjs";
import {
  getTopCardTrendStatusMessage,
  hasRenderableTopCardTrend,
  resolveTopCardWindowState,
} from "./topChaseWindowState.mjs";

// Verbatim production contract for an Ascended Heroes chase card, captured from
// pokemon_set_market_dashboard_snapshot_latest.top_chase_cards_json. The Top
// Chase selector offers seven windows but only 1D/7D/30D are ever persisted as
// canonical marketDeltaWindows, so this fixture is the anchor for both halves
// of the contract: the stored windows must survive the client normalization,
// and the four longer windows must reconstruct from history without the UI
// announcing that they did.
const FIXTURE = JSON.parse(
  fs.readFileSync(new URL("./__fixtures__/ascendedHeroesTopChaseCard.json", import.meta.url), "utf8")
);

// pokemonSetMarketClient is a .js module under a package.json with no "type"
// field, so Node classifies it CommonJS and static named ESM imports of it
// fail to link under the tsx loader (every lib/pokemon/*Client*.test.mjs in
// this repo hits the same wall). Loading it dynamically builds the namespace
// from the runtime exports instead, which resolves correctly.
const { normalizeTopChasePayload } = await import("../../lib/pokemon/pokemonSetMarketClient.js");

function normalizedFixtureCard() {
  const variantId = FIXTURE.card.cardVariantId;
  const payload = normalizeTopChasePayload({
    set: { id: FIXTURE.setId, name: FIXTURE.setName },
    topChaseCards: [FIXTURE.card],
    topChaseCardHistories: { [variantId]: FIXTURE.priceHistory },
    latestMarketDate: FIXTURE.latestMarketDate,
    window: "365d",
    meta: { snapshot: {} },
  });
  return payload.cards[0];
}

function historyPointsFor(card) {
  return (card.priceHistory || []).map((point) => ({
    date: point.date,
    value: point.marketPrice ?? point.price,
  }));
}

function stateFor(card, selectedWindowKey) {
  return resolveTopCardWindowState({
    card,
    historyPoints: historyPointsFor(card),
    selectedWindowKey,
  });
}

test("the persisted 1D/7D/30D windows survive normalizeTopChasePayload", () => {
  const card = normalizedFixtureCard();
  assert.deepEqual(Object.keys(card.marketDeltaWindows).sort(), ["1D", "30D", "7D"]);
  for (const key of ["1D", "7D", "30D"]) {
    assert.equal(stateFor(card, key).source, "stored-canonical");
  }
});

test("snake_case stored windows normalize to the canonical uppercase keys", () => {
  const snakeCard = {
    ...FIXTURE.card,
    marketDeltaWindows: undefined,
    market_delta_windows: Object.fromEntries(
      Object.entries(FIXTURE.card.marketDeltaWindows).map(([key, movement]) => [
        key.toLowerCase(),
        {
          start_date: movement.startDate,
          end_date: movement.endDate,
          change_amount: movement.changeAmount,
          change_percent: movement.changePercent,
          current_price: movement.currentPrice,
          starting_price: movement.startingPrice,
          card_variant_id: movement.cardVariantId,
          condition_id: movement.conditionId,
          is_partial_window: movement.isPartialWindow,
          full_window_coverage: movement.fullWindowCoverage,
        },
      ])
    ),
  };
  const payload = normalizeTopChasePayload({
    set: { id: FIXTURE.setId },
    topChaseCards: [snakeCard],
    topChaseCardHistories: { [FIXTURE.card.cardVariantId]: FIXTURE.priceHistory },
    latestMarketDate: FIXTURE.latestMarketDate,
    meta: { snapshot: {} },
  });
  const card = payload.cards[0];
  assert.deepEqual(Object.keys(card.marketDeltaWindows).sort(), ["1D", "30D", "7D"]);
  assert.equal(stateFor(card, "30D").source, "stored-canonical");
});

test("selectTopChaseCards preserves the normalized stored windows", () => {
  const card = normalizedFixtureCard();
  const selected = selectTopChaseCards({ topChaseCards: [card] });
  assert.deepEqual(Object.keys(selected.cards[0].marketDeltaWindows).sort(), ["1D", "30D", "7D"]);
  assert.equal(stateFor(selected.cards[0], "30D").source, "stored-canonical");
});

test("a valid stored 30D window renders the trend with no status message", () => {
  const state = stateFor(normalizedFixtureCard(), "30D");
  assert.equal(state.source, "stored-canonical");
  assert.equal(state.displayMovement.percent, -6.22);
  assert.equal(hasRenderableTopCardTrend(state), true);
  assert.equal(getTopCardTrendStatusMessage(state), null);
});

test("windows with no persisted contract reconstruct from history silently", () => {
  const card = normalizedFixtureCard();
  // 3M/6M/1Y/lifetime are offered by the selector but are never persisted as
  // canonical windows. Reconstructing them from history is the designed
  // behavior, not a degradation, so nothing may surface to the user.
  for (const key of ["3M", "6M", "1Y", "lifetime"]) {
    const state = stateFor(card, key);
    assert.equal(state.source, "history", `${key} should reconstruct from history`);
    assert.notEqual(state.displayMovement, null, `${key} should still produce a trend`);
    assert.equal(hasRenderableTopCardTrend(state), true, `${key} trend should be renderable`);
    assert.equal(getTopCardTrendStatusMessage(state), null, `${key} must not expose a source diagnostic`);
  }
});

test("a missing stored window falls back to history without user-facing text", () => {
  const card = { ...normalizedFixtureCard(), marketDeltaWindows: null, market_delta_windows: null };
  const state = stateFor(card, "30D");
  assert.equal(state.source, "history_fallback_missing_stored_window");
  assert.ok(state.warnings.includes("missing_stored_window"), "internal warning must be preserved");
  assert.equal(getTopCardTrendStatusMessage(state), null);
});

test("a malformed stored window falls back internally without exposing technical text", () => {
  const base = normalizedFixtureCard();
  const card = {
    ...base,
    marketDeltaWindows: {
      ...base.marketDeltaWindows,
      // endDate before startDate — structurally invalid.
      "30D": { ...base.marketDeltaWindows["30D"], startDate: "2026-08-01", endDate: "2026-07-03" },
    },
  };
  const state = stateFor(card, "30D");
  assert.equal(state.source, "history_fallback_malformed_stored_window");
  assert.ok(state.warnings.includes("malformed_stored_window"), "internal warning must be preserved");
  assert.equal(getTopCardTrendStatusMessage(state), null);
});

test("insufficient history is the only case that reports Trend unavailable", () => {
  const card = { ...normalizedFixtureCard(), marketDeltaWindows: null, market_delta_windows: null };
  const state = resolveTopCardWindowState({
    card,
    historyPoints: [{ date: "2026-08-01", value: 1224.02 }],
    selectedWindowKey: "30D",
  });
  assert.equal(state.source, "insufficient_history");
  assert.equal(hasRenderableTopCardTrend(state), false);
  assert.equal(getTopCardTrendStatusMessage(state), "Trend unavailable for this window.");
});

test("no selectable window ever exposes an internal source diagnostic", () => {
  const card = normalizedFixtureCard();
  const forbidden = [
    "reconstructed from history",
    "window snapshot unavailable",
    "malformed stored window",
    "stored window snapshot was invalid",
    "history fallback",
    "stored-canonical",
    "Trend source",
  ];
  for (const key of STANDARD_DELTA_WINDOW_KEYS) {
    const message = getTopCardTrendStatusMessage(stateFor(card, key));
    if (message === null) continue;
    for (const phrase of forbidden) {
      assert.ok(
        !message.toLowerCase().includes(phrase.toLowerCase()),
        `window ${key} leaked "${phrase}" to the user: ${message}`
      );
    }
  }
});
