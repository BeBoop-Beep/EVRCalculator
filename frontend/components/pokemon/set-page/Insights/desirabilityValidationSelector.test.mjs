import test from "node:test";
import assert from "node:assert/strict";

import { getValidationSetValueMetric, selectDesirabilityValidation } from "./desirabilityValidationSelector.mjs";

test("set value validation prefers explicit canonical checklist fields", () => {
  assert.deepEqual(
    getValidationSetValueMetric({
      currentChecklistSetValue: 120,
      set_value_for_validation: 90,
      simulated_set_value: 999,
    }),
    { key: "currentChecklistSetValue", value: 120, usedCompatibilityFallback: false }
  );
});

test("set value validation accepts snake canonical checklist fields", () => {
  const result = getValidationSetValueMetric({
    current_checklist_set_value: "121.50",
  });

  assert.equal(result.key, "current_checklist_set_value");
  assert.equal(result.value, 121.5);
  assert.equal(result.usedCompatibilityFallback, false);
});

test("simulated set value fallback is explicit in diagnostics", () => {
  const selected = selectDesirabilityValidation(
    [
      { name: "A", desirability_score: 80, currentChecklistSetValue: 100 },
      { name: "B", desirability_score: 70, set_value_for_validation: 90 },
      { name: "C", desirability_score: 60, simulated_set_value: 75 },
    ],
    { metricKey: "setValue" }
  );

  assert.equal(selected.sampleCount, 3);
  assert.equal(selected.diagnostics.compatibilityFallbackRows, 1);
  assert.equal(selected.points.at(-1).ySourceKey, "currentChecklistSetValue");
});

test("desirability validation reports n greater than zero from canonical rows", () => {
  const selected = selectDesirabilityValidation(
    [
      { name: "A", desirability_score: 80, current_checklist_set_value: 100 },
      { name: "B", desirability_score: 70, current_checklist_set_value: 90 },
      { name: "C", desirability_score: 60, current_checklist_set_value: 75 },
    ],
    { metricKey: "setValue" }
  );

  assert.equal(selected.sampleCount, 3);
  assert.equal(selected.diagnostics.rowsWithDesirability, 3);
  assert.equal(selected.diagnostics.rowsWithSelectedMetric, 3);
});
