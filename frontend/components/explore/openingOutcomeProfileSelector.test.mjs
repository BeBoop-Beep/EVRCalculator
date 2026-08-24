import assert from "node:assert/strict";
import test from "node:test";
import { buildOutcomeProfileViewModel, formatOutcomePercent, selectOpeningOutcomeProfileV1 } from "./openingOutcomeProfileSelector.mjs";

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
test("macro outcome groups preserve the exact eight-bucket probability mass", () => {
  const bounds = [[0,.25],[.25,.5],[.5,.75],[.75,1],[1,1.5],[1.5,2],[2,5],[5,null]];
  const selected = selectOpeningOutcomeProfileV1({ ...profile, buckets: bounds.map(([floorRatio, ceilingRatio], i) => ({ key: `b${i}`, label: `${i}`, floorRatio, ceilingRatio, probability: .125, occurrenceCount: 125 })) }, "run-a");
  const view = buildOutcomeProfileViewModel(selected);
  assert.deepEqual(view.groups.map((row) => row.probability), [.25, .25, .25, .25]);
  assert.equal(view.details.length, 8);
  assert.deepEqual(view.groups.map((row) => row.label), ["Under half back", "Half to pack cost", "Pack cost to 2×", "2× or more"]);
});
