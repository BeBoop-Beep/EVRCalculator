import test from "node:test";
import assert from "node:assert/strict";

import { selectCompactSetValue } from "./compactSetValueSelector.mjs";

test("compact set value uses shell fallback when no history exists", () => {
  const selected = selectCompactSetValue({
    history: [],
    fallbackMetric: { key: "summary.currentChecklistSetValue", value: 123.45 },
  });

  assert.equal(selected.value, 123.45);
  assert.equal(selected.sourceKey, "summary.currentChecklistSetValue");
  assert.equal(selected.diagnostics.usedFallback, true);
});

test("compact set value prefers checklist history over fallback", () => {
  const selected = selectCompactSetValue({
    historiesByScope: {
      standard: [
        { date: "2099-01-01", setValue: 100 },
        { date: "2099-01-31", setValue: 130 },
      ],
    },
    fallbackMetric: { key: "summary.currentChecklistSetValue", value: 999 },
  });

  assert.equal(selected.value, 130);
  assert.equal(selected.sourceKey, "setValueHistoriesByScope.standard");
  assert.equal(selected.deltaAmount, 30);
  assert.equal(selected.diagnostics.usedFallback, false);
});

test("compact set value deltas use observed points instead of carried-forward duplicates", () => {
  const selected = selectCompactSetValue({
    historiesByScope: {
      standard: [
        { date: "2026-06-20", setValue: 100 },
        { date: "2026-06-23", setValue: 110 },
        { date: "2026-06-24", setValue: 115 },
        { date: "2026-06-25", setValue: 115, isCarriedForward: true, sourceDate: "2026-06-24" },
        { date: "2026-06-26", setValue: 115, isCarriedForward: true, sourceDate: "2026-06-24" },
      ],
    },
    fallbackMetric: { key: "summary.currentChecklistSetValue", value: 999 },
  });

  assert.equal(selected.value, 115);
  assert.equal(selected.deltaAmount, 15);
  assert.equal(selected.asOf, "2026-06-24");
  assert.equal(selected.visiblePoints.at(-1).date, "2026-06-24");
});

test("compact set value does not show zero delta from one observed point plus carry-forward rows", () => {
  const selected = selectCompactSetValue({
    historiesByScope: {
      standard: [
        { date: "2026-06-24", setValue: 115 },
        { date: "2026-06-25", setValue: 115, isCarriedForward: true, sourceDate: "2026-06-24" },
        { date: "2026-06-26", setValue: 115, isCarriedForward: true, sourceDate: "2026-06-24" },
      ],
    },
  });

  assert.equal(selected.value, 115);
  assert.equal(selected.deltaAmount, null);
  assert.equal(selected.deltaPercent, null);
  assert.equal(selected.asOf, "2026-06-24");
});
