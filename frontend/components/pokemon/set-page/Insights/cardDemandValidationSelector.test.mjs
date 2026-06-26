import test from "node:test";
import assert from "node:assert/strict";

import { selectCardDemandValidation } from "./cardDemandValidationSelector.mjs";

test("card demand validation uses card contract rows independent of Cards tab state", () => {
  const selected = selectCardDemandValidation(
    [
      { name: "A", marketPrice: 10, subjectDemandScore: 80 },
      { name: "B", current_price: 12, pokemon_desirability_score: 70 },
      { name: "C", market_price: 8, cardDesirabilityScore: 60 },
    ],
    { metricKey: "pure", scopeKey: "priced" }
  );

  assert.equal(selected.sampleCount, 3);
  assert.equal(selected.diagnostics.rowsWithMarketPrice, 3);
  assert.equal(selected.diagnostics.rowsWithSelectedMetric, 3);
});

test("card demand validation can use canonical correlation rows", () => {
  const selected = selectCardDemandValidation([], {
    metricKey: "pure",
    scopeKey: "priced",
    correlation: {
      plotRows: [
        { name: "A", marketPrice: 10, subjectDemandScore: 80 },
        { name: "B", marketPrice: 12, subjectDemandScore: 70 },
        { name: "C", marketPrice: 8, subjectDemandScore: 60 },
      ],
    },
  });

  assert.equal(selected.sampleCount, 3);
  assert.equal(selected.diagnostics.source, "canonical_correlation_rows");
});
