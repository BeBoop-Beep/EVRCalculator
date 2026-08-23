import assert from "node:assert/strict";
import test from "node:test";
import { formatOutcomePercent, selectOpeningOutcomeProfileV1 } from "./openingOutcomeProfileSelector.mjs";

const profile = { contractVersion: "opening_outcome_profile_v1", researchMethodVersion: "opening_outcome_profile_research_v1", calculationRunId: "run-a",
  buckets: Array.from({ length: 8 }, (_, i) => ({ key: `b${i}`, label: `${i}`, floorRatio: i, ceilingRatio: i === 7 ? null : i + 1, probability: .125, occurrenceCount: 125 })),
  cumulativeProbabilities: [{ key: "at_least_cost", label: "At least cost", direction: "at_least", thresholdRatio: 1, probability: .25 }] };

test("selects only exact same-run V1 profiles", () => {
  assert.equal(selectOpeningOutcomeProfileV1(profile, "run-a").buckets.length, 8);
  assert.equal(selectOpeningOutcomeProfileV1(profile, "run-b"), null);
  assert.equal(selectOpeningOutcomeProfileV1({ ...profile, contractVersion: "opening_outcome_profile_v2" }, "run-a"), null);
});
test("rejects incomplete probability partitions", () => assert.equal(selectOpeningOutcomeProfileV1({ ...profile, buckets: profile.buckets.slice(1) }, "run-a"), null));
test("formats percentages without fabricating missing values", () => { assert.equal(formatOutcomePercent(.4214), "42.1%"); assert.equal(formatOutcomePercent(null), "Unavailable"); });
