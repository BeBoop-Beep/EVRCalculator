import assert from "node:assert/strict";
import test from "node:test";
import { clipSetMarketDetailHistory, needsLifetimeSetMarketHistory } from "./setMarketDetailHistory.mjs";

function history(days, missingIndex = null) {
  const first = Date.UTC(2026, 0, 1);
  return Array.from({ length: days }, (_, index) => ({
    date: new Date(first + index * 86_400_000).toISOString().slice(0, 10),
    setValue: 100 + index,
  })).filter((_, index) => index !== missingIndex);
}

for (const [label, days] of [["7D", 7], ["30D", 30], ["3M", 90], ["6M", 180]]) {
  test(`${label} detail source retains every daily observation after the global trend would compact`, () => {
    const full = history(200);
    assert.equal(clipSetMarketDetailHistory(full, { startDate: full.at(-days).date, endDate: full.at(-1).date }).length, days);
  });
}

test("a genuinely absent daily observation is not fabricated", () => {
  const full = history(7, 3);
  assert.equal(clipSetMarketDetailHistory(full, { startDate: "2026-01-01", endDate: "2026-01-07" }).length, 6);
  assert.equal(full.some((point) => point.date === "2026-01-04"), false);
});

test("All requests the supported larger window only when 365 days do not reach the known beginning", () => {
  const loaded = history(365);
  assert.equal(needsLifetimeSetMarketHistory({ activeWindowKey: "7D", historyStartDate: "2024-01-01", loadedHistory: loaded, loadedDays: 365 }), false);
  assert.equal(needsLifetimeSetMarketHistory({ activeWindowKey: "lifetime", historyStartDate: "2024-01-01", loadedHistory: loaded, loadedDays: 365 }), true);
  assert.equal(needsLifetimeSetMarketHistory({ activeWindowKey: "lifetime", historyStartDate: loaded[0].date, loadedHistory: loaded, loadedDays: 365 }), false);
});
