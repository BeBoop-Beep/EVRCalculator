import assert from "node:assert/strict";
import test from "node:test";
import { movementTone, selectAssetMarketWindow } from "./assetMarketModel.mjs";

const history = [{ date: "2026-08-01", marketPrice: 10 }, { date: "2026-08-20", marketPrice: 12 }];

test("one selected window owns movement and visible history", () => {
  const selected = selectAssetMarketWindow({ history, movements: { "30D": { available: true, fullCoverage: false, startDate: "2026-08-01", endDate: "2026-08-20", deltaAmount: 2 } } }, "30D");
  assert.equal(selected.movement.deltaAmount, 2);
  assert.deepEqual(selected.history, history);
  assert.equal(selected.partial, true);
});

test("movement tones cover positive negative neutral and absent", () => {
  assert.equal(movementTone({ deltaAmount: 1 }), "positive");
  assert.equal(movementTone({ deltaAmount: -1 }), "negative");
  assert.equal(movementTone({ deltaAmount: 0 }), "neutral");
  assert.equal(movementTone({ deltaAmount: null }), "neutral");
});

test("missing history remains unavailable", () => {
  const selected = selectAssetMarketWindow({ history: [], movements: {} }, "1Y");
  assert.deepEqual(selected.history, []);
  assert.equal(selected.movement.available, false);
});
