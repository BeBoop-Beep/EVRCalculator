import assert from "node:assert/strict";
import test from "node:test";

import { buildMarketValueChangeModel } from "./marketValueChangeModel.mjs";

test("below placement separates the neutral window from the movement text", () => {
  const model = buildMarketValueChangeModel({
    value: 127.13,
    changeAmount: -2.11,
    changePercent: -1.63,
    windowLabel: "30D",
    windowLabelPlacement: "below",
  });
  assert.equal(model.changeText.includes("·"), false);
  assert.equal(model.windowLabel, "30D");
  assert.match(model.accessibleText, /over 30D/);
});

test("below unavailable movement does not duplicate the window", () => {
  const model = buildMarketValueChangeModel({
    value: 127.13,
    windowLabel: "30D",
    windowLabelPlacement: "below",
    unavailable: true,
  });
  assert.equal(model.changeText, "Change unavailable");
  assert.equal(model.windowLabel, "30D");
  assert.match(model.accessibleText, /30-day change unavailable/);
});
