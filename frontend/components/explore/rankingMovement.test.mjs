import assert from "node:assert/strict";
import test from "node:test";
import { buildPreviousSetValueRanks, formatRankMovement, getSetValueMovement } from "./rankingMovement.mjs";

test("rank movement renders improvement, decline, unchanged, and missing history", () => {
  assert.equal(formatRankMovement(5, 3).text, "↑2");
  assert.equal(formatRankMovement(2, 6).text, "↓4");
  assert.equal(formatRankMovement(7, 7).text, "—");
  assert.equal(formatRankMovement(null, 1, "new").text, "NEW");
  assert.equal(formatRankMovement(null, 1, "unavailable").text, "N/A");
});

test("set value movement calculates dollars and percentage without invalid output", () => {
  assert.deepEqual(getSetValueMovement({ checklistSetValue: 264, previousChecklistSetValue7d: 250, setValueComparisonStatus7d: "available" }), { amount: 14, percent: 5.6000000000000005 });
  assert.equal(getSetValueMovement({ checklistSetValue: 264, previousChecklistSetValue7d: 0, setValueComparisonStatus7d: "available" }), null);
  assert.equal(getSetValueMovement({ checklistSetValue: 264, previousChecklistSetValue7d: null, setValueComparisonStatus7d: "available" }), null);
});

test("previous set-value ranks match stable IDs, not display names", () => {
  const ranks = buildPreviousSetValueRanks([
    { set_id: "stable-b", name: "Same", previousChecklistSetValue7d: 200 },
    { set_id: "stable-a", name: "Same", previousChecklistSetValue7d: 300 },
  ]);
  assert.equal(ranks.get("stable-a"), 1);
  assert.equal(ranks.get("stable-b"), 2);
});
