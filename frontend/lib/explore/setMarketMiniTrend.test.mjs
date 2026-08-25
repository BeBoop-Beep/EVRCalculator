import test from "node:test";
import assert from "node:assert/strict";
import { selectSetMarketMiniTrend } from "./setMarketMiniTrend.mjs";

const daily = Array.from({ length: 30 }, (_, index) => [`2026-08-${String(index + 1).padStart(2, "0")}`, 100 + index]);
const target = {
  recentDailyTrend: daily.filter(([date]) => date !== "2026-08-27"),
  trend: [["2026-01-01", 80], ["2026-05-01", 90], ["2026-08-30", 129]],
  windows: {
    "1D": { startDate: "2026-08-29", endDate: "2026-08-30" },
    "7D": { startDate: "2026-08-24", endDate: "2026-08-30" },
    "30D": { startDate: "2026-08-01", endDate: "2026-08-30" },
    "3M": { startDate: "2026-05-01", endDate: "2026-08-30" },
    "6M": { startDate: "2026-01-01", endDate: "2026-08-30" },
    "1Y": { startDate: "2026-01-01", endDate: "2026-08-30" },
    lifetime: { startDate: "2026-01-01", endDate: "2026-08-30" },
  },
};

test("recent windows use real daily points and preserve a missing date", () => {
  assert.equal(selectSetMarketMiniTrend(target, "1D").length, 2);
  assert.equal(selectSetMarketMiniTrend(target, "7D").length, 6);
  assert.equal(selectSetMarketMiniTrend(target, "30D").length, 29);
  assert.ok(!selectSetMarketMiniTrend(target, "7D").some((point) => point.date === "2026-08-27"));
});

test("long windows use and canonically clip the compact trend", () => {
  assert.deepEqual(selectSetMarketMiniTrend(target, "3M").map((point) => point.date), ["2026-05-01", "2026-08-30"]);
  assert.equal(selectSetMarketMiniTrend(target, "6M").length, 3);
  assert.equal(selectSetMarketMiniTrend(target, "1Y").length, 3);
  assert.equal(selectSetMarketMiniTrend(target, "lifetime").length, 3);
});

test("a stale payload cannot silently fall back to compact points for short windows", () => {
  const stale = { ...target, recentDailyTrend: undefined };
  for (const windowKey of ["1D", "7D", "30D"]) assert.deepEqual(selectSetMarketMiniTrend(stale, windowKey), []);
});
