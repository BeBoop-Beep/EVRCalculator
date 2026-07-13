import test from "node:test";
import assert from "node:assert/strict";

import {
  DESIRABILITY_LADDER_SIGNALS,
  buildLadderAriaLabel,
  buildLadderLayout,
  describeLadderSignal,
  estimateLadderLabelWidth,
  selectDesirabilityAlignmentLadder,
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
  rip_core_rank_without_desirability: 18,
  card_appeal_rank: 11,
  strongest_supporting_signal: "Expected Value",
  biggest_conflicting_signal: "Set Value",
  desirability_alignment_band: "moderate",
  desirability_alignment_summary: "This set shows partial market confirmation.",
  desirability_alignment_score: 62.5,
  desirability_alignment_details: {
    set_value_alignment: 57.5,
    top_chase_value_alignment: 67.5,
    expected_value_alignment: 97.5,
    p95_value_alignment: 95,
    top_10_card_value_alignment: 87.5,
  },
};

test("ladder selection plots every ranked signal against the desirability anchor", () => {
  const ladder = selectDesirabilityAlignmentLadder(BASE_VALIDATION);

  assert.ok(ladder, "a full payload must produce a ladder");
  assert.equal(ladder.anchorRank, 14);
  assert.equal(ladder.fieldSize, 40);
  // avg_hit_value_rank is absent from the payload → omitted, no placeholder.
  assert.ok(!ladder.signals.some((signal) => signal.key === "avg_hit_value"));
  const keys = ladder.signals.map((signal) => signal.key);
  for (const expected of ["rip_core", "set_value", "top_chase_value", "top_10_card_value", "p95_value", "expected_value", "card_appeal"]) {
    assert.ok(keys.includes(expected), `signal ${expected} must be plotted`);
  }
});

test("agreement states mirror the backend's named strongest/conflict signals only", () => {
  const ladder = selectDesirabilityAlignmentLadder(BASE_VALIDATION);
  const byKey = new Map(ladder.signals.map((signal) => [signal.key, signal]));

  assert.equal(byKey.get("expected_value").state, "confirms");
  assert.equal(byKey.get("set_value").state, "conflicts");
  for (const key of ["rip_core", "top_chase_value", "top_10_card_value", "p95_value", "card_appeal"]) {
    assert.equal(byKey.get(key).state, "neutral", `${key} must stay neutral`);
  }
  assert.equal(ladder.strongest.key, "expected_value");
  assert.equal(ladder.conflict.key, "set_value");
  // Per-signal alignment scores ride along for tooltips/screen readers.
  assert.equal(byKey.get("set_value").alignmentScore, 57.5);
});

test("camelCase payloads (post-normalizer) resolve the same ladder", () => {
  const ladder = selectDesirabilityAlignmentLadder({
    desirabilityRank: 5,
    totalRankedSets: 20,
    setValueRank: 8,
    expectedValueRank: 4,
    strongestSupportingSignal: "Expected Value",
    biggestConflictingSignal: "Set Value",
    desirabilityAlignmentDetails: { setValueAlignment: 55, expectedValueAlignment: 95 },
  });

  assert.ok(ladder);
  assert.equal(ladder.anchorRank, 5);
  assert.equal(ladder.fieldSize, 20);
  const byKey = new Map(ladder.signals.map((signal) => [signal.key, signal]));
  assert.equal(byKey.get("expected_value").state, "confirms");
  assert.equal(byKey.get("set_value").state, "conflicts");
  assert.equal(byKey.get("set_value").alignmentScore, 55);
});

test("ladder is null without a desirability anchor or without any ranked signal", () => {
  assert.equal(selectDesirabilityAlignmentLadder(null), null);
  assert.equal(selectDesirabilityAlignmentLadder({}), null);
  assert.equal(
    selectDesirabilityAlignmentLadder({ desirability_rank: 3, total_ranked_sets: 10 }),
    null,
    "an anchor with no market signals has nothing to plot"
  );
  assert.equal(
    selectDesirabilityAlignmentLadder({ set_value_rank: 3, total_ranked_sets: 10 }),
    null,
    "signals without an anchor have no reference line"
  );
});

test("field size never truncates a plotted rank, even when total_ranked_sets is stale", () => {
  const ladder = selectDesirabilityAlignmentLadder({
    desirability_rank: 2,
    total_ranked_sets: 10,
    set_value_rank: 14,
  });

  assert.equal(ladder.fieldSize, 14);
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

test("layout maps rank 1 to the left edge, rank N to the right, and staggers labels without overlap", () => {
  const ladder = selectDesirabilityAlignmentLadder(BASE_VALIDATION);
  const layout = buildLadderLayout(ladder, 720);

  assert.ok(layout);
  const byKey = new Map(layout.points.map((point) => [point.key, point]));
  assert.equal(byKey.get("top_chase_value").x, layout.plotLeft, "rank #1 sits at the left edge");
  assert.ok(layout.anchorX > layout.plotLeft && layout.anchorX < layout.plotRight);
  assert.ok(layout.height > 0);

  // No two labels on the same side + lane may overlap horizontally.
  const bySideAndLane = new Map();
  for (const point of layout.points) {
    const key = `${point.side}:${point.lane}`;
    const rows = bySideAndLane.get(key) || [];
    rows.push(point);
    bySideAndLane.set(key, rows);
  }
  for (const rows of bySideAndLane.values()) {
    rows.sort((a, b) => a.labelX - b.labelX);
    for (let index = 1; index < rows.length; index += 1) {
      const previous = rows[index - 1];
      const current = rows[index];
      const previousEnd = previous.labelX + estimateLadderLabelWidth(previous.labelText) / 2;
      const currentStart = current.labelX - estimateLadderLabelWidth(current.labelText) / 2;
      assert.ok(currentStart >= previousEnd, `labels must not overlap: ${previous.labelText} / ${current.labelText}`);
    }
  }
});

test("layout stays overlap-free at mobile widths and null at zero width", () => {
  const ladder = selectDesirabilityAlignmentLadder(BASE_VALIDATION);
  const layout = buildLadderLayout(ladder, 320);

  assert.ok(layout, "mobile widths still lay out");
  for (const point of layout.points) {
    const halfWidth = estimateLadderLabelWidth(point.labelText) / 2;
    assert.ok(point.labelX - halfWidth >= 0, `${point.labelText} must not clip the left edge`);
    assert.ok(point.labelX + halfWidth <= 320, `${point.labelText} must not clip the right edge`);
  }

  assert.equal(buildLadderLayout(ladder, 0), null);
  assert.equal(buildLadderLayout(null, 720), null);
});

test("coincident ranks fan dots vertically so both stay visible", () => {
  const ladder = selectDesirabilityAlignmentLadder({
    desirability_rank: 5,
    total_ranked_sets: 20,
    set_value_rank: 7,
    expected_value_rank: 7,
  });
  const layout = buildLadderLayout(ladder, 600);
  const [first, second] = layout.points;

  assert.equal(first.x, second.x);
  assert.notEqual(first.dotY, second.dotY);
});

test("accessible descriptions carry rank, field size, alignment, and agreement state", () => {
  const ladder = selectDesirabilityAlignmentLadder(BASE_VALIDATION);
  const setValue = ladder.signals.find((signal) => signal.key === "set_value");

  const description = describeLadderSignal(setValue, ladder.fieldSize);
  assert.ok(description.includes("Set value rank #31 of 40"));
  assert.ok(description.includes("alignment 58 of 100"));
  assert.ok(description.includes("biggest conflicting signal"));

  const ariaLabel = buildLadderAriaLabel(ladder);
  assert.ok(ariaLabel.includes("anchor at rank #14 of 40"));
  assert.ok(ariaLabel.includes("EV rank #15 of 40"));
  assert.equal(buildLadderAriaLabel(null), "");
});

test("signal config covers the documented backend rank fields", () => {
  const rankKeys = DESIRABILITY_LADDER_SIGNALS.flatMap((signal) => signal.rankKeys);
  for (const expected of [
    "set_value_rank",
    "top_chase_value_rank",
    "top_10_card_value_rank",
    "avg_hit_value_rank",
    "p95_rank",
    "expected_value_rank",
    "rip_core_rank_without_desirability",
    "card_appeal_rank",
  ]) {
    assert.ok(rankKeys.includes(expected), `missing rank key ${expected}`);
  }
});
