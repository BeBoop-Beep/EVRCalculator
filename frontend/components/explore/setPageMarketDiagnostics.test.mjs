import test from "node:test";
import assert from "node:assert/strict";

import { buildSetPageMarketDiagnostics, getHistoryPointsEndDate } from "./setPageMarketDiagnostics.mjs";

const alignedInput = {
  setId: "set-1",
  generationId: "gen-1",
  marketAsOfDate: "2026-07-13",
  titleCardEndDate: "2026-07-13",
  setValueEndDate: "2026-07-13",
  openingProfitEndDate: "2026-07-13",
  topChaseEndDate: "2026-07-13",
  cardsSnapshotEndDate: "2026-07-13",
  totalCards: 190,
  cardsWith7dMovement: 165,
  nonzero7dMovers: 160,
  marketMoversFilteredTotal: 160,
  bannerCount: 10,
  bannerFirstTenIds: ["a", "b", "c"],
  cardsFirstTenIds: ["a", "b", "c"],
  usedLegacyMoverList: false,
  isMixedGenerations: false,
};

test("aligned surfaces produce datesAligned=true and no warnings", () => {
  const { diagnostics, warnings } = buildSetPageMarketDiagnostics(alignedInput);

  assert.equal(diagnostics.datesAligned, true);
  assert.equal(diagnostics.bannerMatchesCards, true);
  assert.deepEqual(warnings, []);
});

test("a chart ending past marketAsOfDate warns that the point exceeds the canonical date", () => {
  const { diagnostics, warnings } = buildSetPageMarketDiagnostics({
    ...alignedInput,
    topChaseEndDate: "2026-07-14",
  });

  assert.equal(diagnostics.datesAligned, false);
  assert.ok(warnings.some((warning) => warning.includes("topChaseEndDate") && warning.includes("exceeds marketAsOfDate")));
});

test("a chart ending before marketAsOfDate also warns (every surface must share one end date)", () => {
  const { warnings } = buildSetPageMarketDiagnostics({
    ...alignedInput,
    setValueEndDate: "2026-07-12",
  });

  assert.ok(warnings.some((warning) => warning.includes("setValueEndDate") && warning.includes("ends before")));
});

test("Market Movers total differing from the canonical nonzero movement count warns", () => {
  const { warnings } = buildSetPageMarketDiagnostics({
    ...alignedInput,
    marketMoversFilteredTotal: 22,
    nonzero7dMovers: 160,
  });

  assert.ok(warnings.some((warning) => warning.includes("differs from the canonical nonzero 7D movement filter")));
});

test("banner order mismatch against the Cards first ten warns", () => {
  const { diagnostics, warnings } = buildSetPageMarketDiagnostics({
    ...alignedInput,
    bannerFirstTenIds: ["a", "c", "b"],
  });

  assert.equal(diagnostics.bannerMatchesCards, false);
  assert.ok(warnings.some((warning) => warning.includes("banner first ten differ")));
});

test("banner parity is not asserted when the Cards movers view is not loaded", () => {
  const { diagnostics, warnings } = buildSetPageMarketDiagnostics({
    ...alignedInput,
    cardsFirstTenIds: null,
  });

  assert.equal(diagnostics.bannerMatchesCards, null);
  assert.ok(!warnings.some((warning) => warning.includes("banner first ten")));
});

test("legacy mover membership and mixed generations each warn", () => {
  const { warnings } = buildSetPageMarketDiagnostics({
    ...alignedInput,
    usedLegacyMoverList: true,
    isMixedGenerations: true,
  });

  assert.ok(warnings.some((warning) => warning.includes("legacy mover list")));
  assert.ok(warnings.some((warning) => warning.includes("Mixed snapshot generations")));
});

test("getHistoryPointsEndDate returns the max valid date key", () => {
  assert.equal(
    getHistoryPointsEndDate([
      { date: "2026-07-11" },
      { date: "2026-07-13" },
      { date: "not-a-date" },
      { date: "2026-07-12" },
    ]),
    "2026-07-13"
  );
  assert.equal(getHistoryPointsEndDate([]), null);
});
