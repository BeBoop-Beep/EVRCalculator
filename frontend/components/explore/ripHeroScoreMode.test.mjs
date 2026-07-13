import assert from "node:assert/strict";
import test from "node:test";

import {
  RIP_CORE_MODE,
  RIP_SCORE_MODE,
  selectRipHeroScoreMode,
} from "./ripHeroScoreMode.mjs";

const summary = {
  relative_pack_score: 72.4,
  pack_rank: 18,
  pack_tier: "D",
  rip_score_without_desirability: 18.55,
  relative_rip_core_score: 61.2,
  rip_core_rank: 15,
  rip_core_tier: "C",
  rip_core_interpretation: { label: "Financially mixed", summary: "Core summary", severity: "neutral" },
};

test("RIP Score and RIP Core switch score, rank, tier, helper, and interpretation", () => {
  const finalMode = selectRipHeroScoreMode({ mode: RIP_SCORE_MODE, summary });
  const coreMode = selectRipHeroScoreMode({ mode: RIP_CORE_MODE, summary });

  assert.equal(finalMode.score, 72.4);
  assert.equal(finalMode.rank, 18);
  assert.equal(finalMode.tier, "D");
  assert.match(finalMode.helper, /collector desirability/);
  assert.equal(coreMode.score, 61.2);
  assert.equal(coreMode.rank, 15);
  assert.equal(coreMode.tier, "C");
  assert.equal(coreMode.interpretation.summary, "Core summary");
  assert.match(coreMode.helper, /without collector desirability/);
});

test("RIP Core never displays the raw canonical comparison score on the presentation scale", () => {
  const selected = selectRipHeroScoreMode({
    mode: RIP_CORE_MODE,
    summary: { rip_score_without_desirability: 18.55, rip_core_rank: 15 },
  });

  assert.equal(selected.mode, RIP_SCORE_MODE);
  assert.equal(selected.score, null);
});

test("RIP Core selection resets to RIP Score when the next set lacks the normalized contract", () => {
  const selected = selectRipHeroScoreMode({ mode: RIP_CORE_MODE, summary: { relative_pack_score: 80 } });
  assert.equal(selected.mode, RIP_SCORE_MODE);
  assert.equal(selected.score, 80);
});
