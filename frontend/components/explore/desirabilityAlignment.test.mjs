import test from "node:test";
import assert from "node:assert/strict";

import {
  DESIRABILITY_AGREEMENT_SIGNALS,
  buildAgreementAriaLabel,
  buildDivergingAgreementModel,
  describeAgreementSignal,
  selectDesirabilityAgreement,
  selectDesirabilityVerdict,
} from "./desirabilityAlignment.mjs";

const BASE_VALIDATION = {
  desirability_rank: 14,
  total_ranked_sets: 40,
  set_value_rank: 31,
  top_chase_value_rank: 1,
  top_10_card_value_rank: 9,
  p95_rank: 12,
  expected_value_rank: 15,
  strongest_supporting_signal: "Expected Value",
  biggest_conflicting_signal: "Set Value",
  desirability_alignment_band: "moderate",
  desirability_alignment_summary: "This set shows partial market confirmation.",
  desirability_alignment_score: 62.5,
  desirability_alignment_details: {
    set_value_alignment: 42.5,
    top_chase_value_alignment: 67.5,
    expected_value_alignment: 97.5,
    p95_value_alignment: 95,
    top_10_card_value_alignment: 87.5,
  },
};

test("agreement selection returns one row per engine-scored signal, sorted strongest first", () => {
  const agreement = selectDesirabilityAgreement(BASE_VALIDATION);

  assert.ok(agreement, "a full payload must produce an agreement view");
  assert.equal(agreement.anchorRank, 14);
  assert.equal(agreement.fieldSize, 40);
  // avg_hit_value has no engine alignment in the payload → omitted, no
  // placeholder and no fabricated bar.
  assert.ok(!agreement.signals.some((signal) => signal.key === "avg_hit_value"));
  const keys = agreement.signals.map((signal) => signal.key);
  assert.deepEqual(keys, ["expected_value", "p95_value", "top_10_card_value", "top_chase_value", "set_value"]);
  // Ranks ride along as supporting labels.
  const topChase = agreement.signals.find((signal) => signal.key === "top_chase_value");
  assert.equal(topChase.rank, 1);
});

test("agreement states mirror the backend's named strongest/conflict signals only", () => {
  const agreement = selectDesirabilityAgreement(BASE_VALIDATION);
  const byKey = new Map(agreement.signals.map((signal) => [signal.key, signal]));

  assert.equal(byKey.get("expected_value").state, "confirms");
  assert.equal(byKey.get("set_value").state, "conflicts");
  for (const key of ["top_chase_value", "top_10_card_value", "p95_value"]) {
    assert.equal(byKey.get(key).state, "neutral", `${key} must stay neutral`);
  }
  assert.equal(agreement.strongest.key, "expected_value");
  assert.equal(agreement.conflict.key, "set_value");
});

test("diverging model is an affine display transform of the engine score around its midpoint", () => {
  const model = buildDivergingAgreementModel(selectDesirabilityAgreement(BASE_VALIDATION));
  const byKey = new Map(model.rows.map((row) => [row.key, row]));

  // score > 50 → right/confirm side; score < 50 → left/conflict side; length
  // is |score − 50| × 2 percent of the half-axis. The engine score itself is
  // preserved untouched on every row.
  assert.equal(byKey.get("expected_value").side, "confirms");
  assert.equal(byKey.get("expected_value").extentPercent, 95);
  assert.equal(byKey.get("expected_value").alignmentScore, 97.5);
  assert.equal(byKey.get("set_value").side, "conflicts");
  assert.equal(byKey.get("set_value").extentPercent, 15);
  assert.equal(byKey.get("set_value").alignmentScore, 42.5);
  assert.equal(byKey.get("top_chase_value").side, "confirms");
  assert.equal(byKey.get("top_chase_value").extentPercent, 35);
});

test("a #1 top chase the engine scores as full agreement renders as a strong confirm, never the outlier", () => {
  // The exact regression being guarded: desirability #1 + top chase #1 → the
  // engine outputs alignment 100 and names top chase the strongest signal. The
  // display must put it on the confirm side at full extent.
  const model = buildDivergingAgreementModel(
    selectDesirabilityAgreement({
      desirability_rank: 1,
      total_ranked_sets: 33,
      top_chase_value_rank: 1,
      set_value_rank: 20,
      strongest_supporting_signal: "Top Chase Value",
      biggest_conflicting_signal: "Set Value",
      desirability_alignment_details: {
        top_chase_value_alignment: 100,
        set_value_alignment: 42.4,
      },
    })
  );
  const topChase = model.rows.find((row) => row.key === "top_chase_value");

  assert.equal(topChase.side, "confirms");
  assert.equal(topChase.extentPercent, 100);
  assert.equal(topChase.state, "confirms");
  assert.equal(model.rows[0].key, "top_chase_value", "the strongest confirm leads the row order");
  const setValue = model.rows.find((row) => row.key === "set_value");
  assert.equal(setValue.side, "conflicts");
});

test("display-only guard: bar geometry consumes the engine's alignment output, never re-derived from ranks", () => {
  // Deliberately inconsistent payload: the ranks are identical (a rank-based
  // recomputation would yield full agreement) but the engine's score says 20.
  // The display must follow the engine score — proof no new agreement math
  // runs on the frontend.
  const model = buildDivergingAgreementModel(
    selectDesirabilityAgreement({
      desirability_rank: 5,
      total_ranked_sets: 20,
      expected_value_rank: 5,
      desirability_alignment_details: { expected_value_alignment: 20 },
    })
  );
  const row = model.rows[0];

  assert.equal(row.alignmentScore, 20);
  assert.equal(row.side, "conflicts");
  assert.equal(row.extentPercent, 60);

  // And a signal with a rank but no engine magnitude gets no bar at all.
  const withoutMagnitude = selectDesirabilityAgreement({
    desirability_rank: 5,
    total_ranked_sets: 20,
    expected_value_rank: 5,
    set_value_rank: 6,
    desirability_alignment_details: { expected_value_alignment: 80 },
  });
  assert.ok(!withoutMagnitude.signals.some((signal) => signal.key === "set_value"));
});

test("camelCase payloads (post-normalizer) resolve the same agreement view", () => {
  const agreement = selectDesirabilityAgreement({
    desirabilityRank: 5,
    totalRankedSets: 20,
    setValueRank: 8,
    expectedValueRank: 4,
    strongestSupportingSignal: "Expected Value",
    biggestConflictingSignal: "Set Value",
    desirabilityAlignmentDetails: { setValueAlignment: 45, expectedValueAlignment: 95 },
  });

  assert.ok(agreement);
  assert.equal(agreement.anchorRank, 5);
  assert.equal(agreement.fieldSize, 20);
  const byKey = new Map(agreement.signals.map((signal) => [signal.key, signal]));
  assert.equal(byKey.get("expected_value").state, "confirms");
  assert.equal(byKey.get("expected_value").alignmentScore, 95);
  assert.equal(byKey.get("set_value").state, "conflicts");
  assert.equal(byKey.get("set_value").rank, 8);
});

test("agreement view is null without any engine-scored signal", () => {
  assert.equal(selectDesirabilityAgreement(null), null);
  assert.equal(selectDesirabilityAgreement({}), null);
  assert.equal(
    selectDesirabilityAgreement({ desirability_rank: 3, total_ranked_sets: 10, set_value_rank: 4 }),
    null,
    "ranks alone carry no engine agreement magnitude — nothing honest to plot"
  );
  assert.equal(buildDivergingAgreementModel(null), null);
});

test("a midpoint score renders no bar in either direction", () => {
  const model = buildDivergingAgreementModel(
    selectDesirabilityAgreement({
      desirability_rank: 3,
      total_ranked_sets: 10,
      expected_value_rank: 8,
      desirability_alignment_details: { expected_value_alignment: 50 },
    })
  );

  assert.equal(model.rows[0].extentPercent, 0);
  assert.equal(model.rows[0].side, "confirms");
});

test("verdict binds the backend band, signals, and summary; single-signal payloads drop the outlier clause", () => {
  const verdict = selectDesirabilityVerdict(BASE_VALIDATION);
  assert.equal(verdict.band, "moderate");
  assert.equal(verdict.label, "Partly confirmed");
  assert.equal(verdict.strongestLabel, "EV");
  assert.equal(verdict.conflictLabel, "Set value");
  assert.equal(verdict.summary, "This set shows partial market confirmation.");

  const single = selectDesirabilityVerdict({
    ...BASE_VALIDATION,
    strongest_supporting_signal: "Expected Value",
    biggest_conflicting_signal: "Expected Value",
  });
  assert.equal(single.conflictLabel, null, "same signal on both ends is not an outlier");

  assert.equal(selectDesirabilityVerdict({}), null);
});

test("accessible descriptions carry the engine score, side, rank, and named state", () => {
  const model = buildDivergingAgreementModel(selectDesirabilityAgreement(BASE_VALIDATION));
  const setValue = model.rows.find((row) => row.key === "set_value");

  const description = describeAgreementSignal(setValue, model.fieldSize);
  assert.ok(description.includes("Set value: agreement 43 of 100"));
  assert.ok(description.includes("conflicts with the desirability read"));
  assert.ok(description.includes("rank #31 of 40"));
  assert.ok(description.includes("biggest conflicting signal"));

  const ariaLabel = buildAgreementAriaLabel(model);
  assert.ok(ariaLabel.includes("desirability rank #14 of 40"));
  assert.ok(ariaLabel.includes("Bars right of center confirm the desirability read"));
  assert.ok(ariaLabel.includes("EV: agreement 98 of 100"));
  assert.equal(buildAgreementAriaLabel(null), "");
});

test("signal config covers exactly the backend's engine-scored market signals", () => {
  const keys = DESIRABILITY_AGREEMENT_SIGNALS.map((signal) => signal.key);
  assert.deepEqual(
    keys.sort(),
    ["avg_hit_value", "expected_value", "p95_value", "set_value", "top_10_card_value", "top_chase_value"].sort()
  );
  for (const signal of DESIRABILITY_AGREEMENT_SIGNALS) {
    assert.ok(signal.alignmentKeys.length >= 2, `${signal.key} must read the engine magnitude in both casings`);
    assert.ok(signal.rankKeys.length >= 2, `${signal.key} must read its rank in both casings`);
  }
});
