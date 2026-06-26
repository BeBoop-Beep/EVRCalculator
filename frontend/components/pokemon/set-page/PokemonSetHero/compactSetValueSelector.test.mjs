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
