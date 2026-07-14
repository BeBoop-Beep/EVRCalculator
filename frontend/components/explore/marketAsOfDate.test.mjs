import test from "node:test";
import assert from "node:assert/strict";

import {
  clampHistoryPointsToDate,
  getMarketDateSourceFromPayload,
  resolveMarketAsOfDate,
} from "./marketAsOfDate.mjs";

test("one coordinated generation resolves to its single shared marketAsOfDate", () => {
  const resolution = resolveMarketAsOfDate([
    { key: "overview", generationId: "gen-1", marketAsOfDate: "2026-07-13" },
    { key: "topChase", generationId: "gen-1", marketAsOfDate: "2026-07-13" },
    { key: "marketMovers", generationId: "gen-1", marketAsOfDate: "2026-07-13" },
  ]);

  assert.equal(resolution.marketAsOfDate, "2026-07-13");
  assert.equal(resolution.isMixedGenerations, false);
  assert.equal(resolution.isMixedDates, false);
});

test("mixed legacy snapshots pick the MINIMUM authoritative market date as the shared cutoff", () => {
  // Journey Together scenario: an older section still reports July 14 while
  // the coordinated generation says July 13 — every surface clamps to July 13.
  const resolution = resolveMarketAsOfDate([
    { key: "overview", generationId: "gen-2", marketAsOfDate: "2026-07-13" },
    { key: "topChase", generationId: "gen-1", marketAsOfDate: "2026-07-14" },
  ]);

  assert.equal(resolution.marketAsOfDate, "2026-07-13");
  assert.equal(resolution.isMixedGenerations, true);
  assert.equal(resolution.isMixedDates, true);
});

test("missing sources resolve to null — never to runtime today", () => {
  const resolution = resolveMarketAsOfDate([]);
  assert.equal(resolution.marketAsOfDate, null);
  assert.equal(resolution.isMixedGenerations, false);
});

test("sources without a market date are ignored", () => {
  const resolution = resolveMarketAsOfDate([
    null,
    { key: "cards", generationId: "gen-1", marketAsOfDate: null },
    { key: "overview", generationId: "gen-1", marketAsOfDate: "2026-07-13" },
  ]);
  assert.equal(resolution.marketAsOfDate, "2026-07-13");
  assert.equal(resolution.sources.length, 1);
});

test("payload extraction prefers snapshot.marketAsOfDate, then movementAsOfDate, then latestMarketDate", () => {
  assert.deepEqual(
    getMarketDateSourceFromPayload("overview", {
      latestMarketDate: "2026-07-14",
      meta: { snapshot: { generationId: "gen-9", marketAsOfDate: "2026-07-13" } },
    }),
    { key: "overview", generationId: "gen-9", marketAsOfDate: "2026-07-13" }
  );
  assert.deepEqual(
    getMarketDateSourceFromPayload("topChase", {
      meta: { snapshot: { movementAsOfDate: "2026-07-12" } },
    }),
    { key: "topChase", generationId: null, marketAsOfDate: "2026-07-12" }
  );
  assert.deepEqual(
    getMarketDateSourceFromPayload("movers", { latestMarketDate: "2026-07-11", meta: {} }),
    { key: "movers", generationId: null, marketAsOfDate: "2026-07-11" }
  );
  assert.equal(getMarketDateSourceFromPayload("cards", { meta: {} }), null);
  assert.equal(getMarketDateSourceFromPayload("cards", null), null);
});

test("payload extraction never reads request time, updated_at, or runtime today", () => {
  const source = getMarketDateSourceFromPayload("overview", {
    meta: { snapshot: { updatedAt: "2026-07-14T02:00:00Z" } },
  });
  assert.equal(source, null);
});

test("clampHistoryPointsToDate drops points beyond the cutoff and never mutates the input", () => {
  const input = [
    { date: "2026-07-12", value: 1 },
    { date: "2026-07-13", value: 2 },
    { date: "2026-07-14", value: 3 },
  ];
  const snapshot = JSON.stringify(input);
  const clamped = clampHistoryPointsToDate(input, "2026-07-13");

  assert.deepEqual(clamped.map((point) => point.date), ["2026-07-12", "2026-07-13"]);
  assert.equal(JSON.stringify(input), snapshot);
  // No cutoff / nothing to clamp returns the original array untouched.
  assert.equal(clampHistoryPointsToDate(input, null), input);
  assert.equal(clampHistoryPointsToDate(input.slice(0, 2), "2026-07-13").length, 2);
});
