import test from "node:test";
import assert from "node:assert/strict";

import { compareMarketFreshnessMetadata } from "./marketAsOfDate.mjs";
import {
  chooseFresherOverviewPayload,
  getOverviewFreshnessMetadata,
} from "./performanceHistorySelector.mjs";

// Regression contract for "the database is current but Overview still shows
// the previous market date".
//
// chooseFresherMarketPayload compares marketAsOfDate only. A market-dashboard
// snapshot advertises the promoted market date it was built against, while its
// Opening Profit vs Cost history is assembled from simulation rows — so two
// payloads can tie on marketAsOfDate while one's OPvC series ends a day earlier.
// That tie is exactly the shape a cached /overview response has after the row
// has been rebuilt.

function overviewPayload({ history, marketDate = "2026-08-02", updatedAt = null, generationId = "gen-1" }) {
  return {
    performanceVsCostHistory: history,
    latestMarketDate: marketDate,
    meta: {
      snapshot: {
        generationId,
        marketAsOfDate: marketDate,
        ...(updatedAt ? { updatedAt } : {}),
      },
    },
  };
}

const AUG_1_HISTORY = [
  { date: "2026-07-31", meanValueToCostRatio: 0.79 },
  { date: "2026-08-01", meanValueToCostRatio: 0.82 },
];

const AUG_2_HISTORY = [
  ...AUG_1_HISTORY,
  { date: "2026-08-02", meanValueToCostRatio: 0.88 },
];

test("the payload whose OPvC history ends later wins on an equal market date", () => {
  // Both claim 2026-08-02. Only one actually has an 08-02 OPvC point.
  const staleSeed = overviewPayload({ history: AUG_1_HISTORY });
  const currentLive = overviewPayload({ history: AUG_2_HISTORY });

  assert.equal(chooseFresherOverviewPayload(staleSeed, currentLive), currentLive);
  // ...and the same holds when the STALE one is the live response, which is the
  // stale-while-revalidate case a market-date-only comparison got wrong.
  assert.equal(chooseFresherOverviewPayload(currentLive, staleSeed), currentLive);
});

test("a carried-forward point never establishes OPvC freshness", () => {
  const carriedToAug2 = overviewPayload({
    history: [...AUG_1_HISTORY, { date: "2026-08-02", meanValueToCostRatio: 0.82, isCarriedForward: true }],
  });
  const realAug2 = overviewPayload({ history: AUG_2_HISTORY });

  assert.equal(getOverviewFreshnessMetadata(carriedToAug2).latestRealHistoryDate, "2026-08-01");
  assert.equal(getOverviewFreshnessMetadata(realAug2).latestRealHistoryDate, "2026-08-02");
  assert.equal(chooseFresherOverviewPayload(carriedToAug2, realAug2), realAug2);
  assert.equal(chooseFresherOverviewPayload(realAug2, carriedToAug2), realAug2);
});

test("snapshot updatedAt breaks a tie on history date, before market date", () => {
  const older = overviewPayload({ history: AUG_2_HISTORY, updatedAt: "2026-08-02T04:00:00Z" });
  const newer = overviewPayload({ history: AUG_2_HISTORY, updatedAt: "2026-08-02T09:00:00Z" });

  assert.equal(chooseFresherOverviewPayload(newer, older), newer);
  assert.equal(chooseFresherOverviewPayload(older, newer), newer);
});

test("market date still decides when history and updatedAt are indistinguishable", () => {
  const aug1 = overviewPayload({ history: AUG_1_HISTORY, marketDate: "2026-08-01" });
  const aug2 = overviewPayload({ history: AUG_1_HISTORY, marketDate: "2026-08-02" });

  assert.equal(chooseFresherOverviewPayload(aug2, aug1), aug2);
});

test("point count is the final deterministic tie-breaker", () => {
  const shorter = overviewPayload({ history: [{ date: "2026-08-02" }] });
  const longer = overviewPayload({ history: [{ date: "2026-08-01" }, { date: "2026-08-02" }] });

  assert.equal(chooseFresherOverviewPayload(longer, shorter), longer);
  assert.equal(chooseFresherOverviewPayload(shorter, longer), longer);
});

test("a genuine tie on every signal keeps the just-fetched live payload", () => {
  const seed = overviewPayload({ history: AUG_2_HISTORY });
  const live = overviewPayload({ history: AUG_2_HISTORY });

  assert.equal(chooseFresherOverviewPayload(seed, live), live);
  assert.equal(compareMarketFreshnessMetadata(getOverviewFreshnessMetadata(seed), getOverviewFreshnessMetadata(live)), 0);
});

test("a missing payload on either side is handled without inventing freshness", () => {
  const seed = overviewPayload({ history: AUG_2_HISTORY });
  assert.equal(chooseFresherOverviewPayload(seed, null), seed);
  assert.equal(chooseFresherOverviewPayload(null, seed), seed);
  assert.equal(chooseFresherOverviewPayload(null, null), null);
});

test("metadata derivation reports every declared signal", () => {
  const metadata = getOverviewFreshnessMetadata(
    overviewPayload({ history: AUG_2_HISTORY, updatedAt: "2026-08-02T09:00:00Z" })
  );

  assert.equal(metadata.latestRealHistoryDate, "2026-08-02");
  assert.equal(metadata.marketAsOfDate, "2026-08-02");
  assert.equal(metadata.historyPointCount, 3);
  assert.equal(typeof metadata.snapshotUpdatedAt, "number");
});
