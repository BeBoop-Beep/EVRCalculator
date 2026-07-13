import assert from "node:assert/strict";
import test from "node:test";

import {
  MARKET_VALUE_CHANGE_VARIANTS,
  buildMarketValueChangeModel,
} from "./marketValueChangeModel.mjs";

test("formats a positive value with matching amount, percentage, window, and accessible direction", () => {
  const model = buildMarketValueChangeModel({ value: 7727.45, changeAmount: 495.26, changePercent: 6.8, windowLabel: "30D" });
  assert.equal(model.valueText, "$7,727.45");
  assert.equal(model.changeText, "\u25b2 +$495.26 (+6.8%) \u00b7 30D");
  assert.match(model.accessibleText, /Positive change/);
});

test("formats a negative value with the project minus character", () => {
  const model = buildMarketValueChangeModel({ value: 7232.19, changeAmount: -495.26, changePercent: -6.4, windowLabel: "30D" });
  assert.equal(model.changeText, "\u25bc \u2212$495.26 (\u22126.4%) \u00b7 30D");
  assert.match(model.accessibleText, /Negative change/);
});

test("formats zero movement neutrally without a triangle", () => {
  const model = buildMarketValueChangeModel({ value: 124.05, changeAmount: 0, changePercent: 0, windowLabel: "7D" });
  assert.equal(model.changeText, "\u2014 $0.00 (0.0%) \u00b7 7D");
  assert.equal(model.direction, "neutral");
  assert.match(model.accessibleText, /No change/);
});

test("marks movement unavailable unless both amount and percentage are reliable", () => {
  const model = buildMarketValueChangeModel({ value: 124.05, changeAmount: null, changePercent: 4.7, windowLabel: "7D" });
  assert.equal(model.changeText, "7D change unavailable");
  assert.equal(model.hasReliableChange, false);
});

test("declares every supported visual size variant", () => {
  assert.deepEqual(MARKET_VALUE_CHANGE_VARIANTS, ["hero", "chart-summary", "table-row", "card-tile", "ticker", "tooltip"]);
});
