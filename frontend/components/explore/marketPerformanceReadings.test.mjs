import test from "node:test";
import assert from "node:assert/strict";
import { orderMarketPerformanceReadings } from "./marketPerformanceReadings.mjs";

test("tooltip readings follow the drawn vertical order at every inspected date", () => {
  const keys = (rows) => orderMarketPerformanceReadings(rows).map((row) => row.key);
  assert.deepEqual(keys([{ key: "red", value: 130 }, { key: "green", value: 120 }, { key: "purple", value: 110 }]), ["red", "green", "purple"]);
  assert.deepEqual(keys([{ key: "red", value: 120 }, { key: "green", value: 110 }, { key: "purple", value: 130 }]), ["purple", "red", "green"]);
  assert.deepEqual(keys([{ key: "missing", value: null }, { key: "b", value: 100 }, { key: "a", value: 100 }]), ["a", "b", "missing"]);
});
test("focus exposes only the focused market to visual and spoken tooltip consumers", () => {
  const rows = [{ key: "red", value: 130 }, { key: "green", value: 120 }, { key: "purple", value: 110 }];
  assert.deepEqual(orderMarketPerformanceReadings(rows, "green").map((row) => row.key), ["green"]);
});
