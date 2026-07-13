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

test("formats an amount-only change without fabricating a percentage", () => {
  const model = buildMarketValueChangeModel({ value: 124.05, changeAmount: 4.2, changePercent: null, windowLabel: "30D", accessibleLabel: "Card market price" });
  assert.equal(model.changeText, "\u25b2 +$4.20 \u00b7 30D");
  assert.equal(model.amountText, "+$4.20");
  assert.equal(model.percentText, null);
  assert.equal(model.accessibleText, "Card market price: $124.05. Positive change, +$4.20 over 30D.");
});

test("formats a percentage-only change and derives direction from percentage", () => {
  const model = buildMarketValueChangeModel({ value: 124.05, changeAmount: null, changePercent: 4.7, windowLabel: "7D" });
  assert.equal(model.changeText, "\u25b2 +4.7% \u00b7 7D");
  assert.equal(model.amountText, null);
  assert.equal(model.percentText, "+4.7%");
  assert.equal(model.direction, "positive");
  assert.equal(model.accessibleText, "Market value: $124.05. Positive change, +4.7% over 7D.");
});

test("marks movement unavailable when neither delta value exists", () => {
  const model = buildMarketValueChangeModel({ value: 124.05, changeAmount: null, changePercent: null, windowLabel: "7D" });
  assert.equal(model.changeText, "7D change unavailable");
  assert.equal(model.hasReliableChange, false);
});

test("explicit unavailable state overrides populated movement fields", () => {
  const model = buildMarketValueChangeModel({ value: 124.05, changeAmount: 4.2, changePercent: 3.5, windowLabel: "30D", unavailable: true });
  assert.equal(model.changeText, "30D change unavailable");
  assert.equal(model.direction, "unavailable");
  assert.match(model.accessibleText, /30D change unavailable/);
});

test("uses an explicit partial-history period without claiming a full window", () => {
  const model = buildMarketValueChangeModel({
    value: 124.05,
    changeAmount: 4.2,
    changePercent: 3.5,
    windowLabel: "30D",
    accessiblePeriodLabel: "since the first available price, covering 14 days",
  });
  assert.equal(
    model.accessibleText,
    "Market value: $124.05. Positive change, +$4.20, +3.5% since the first available price, covering 14 days."
  );
  assert.doesNotMatch(model.accessibleText, /over 30D/);
  assert.equal(model.windowLabel, "30D");
});

test("declares every supported visual size variant", () => {
  assert.deepEqual(MARKET_VALUE_CHANGE_VARIANTS, ["hero", "chart-summary", "table-row", "card-tile", "ticker", "tooltip"]);
});
