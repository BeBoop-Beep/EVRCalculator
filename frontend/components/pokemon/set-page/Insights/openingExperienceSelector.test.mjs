import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import {
  selectCollectorAppealImpact,
  selectOpeningExperiencePresentation,
} from "./openingExperienceSelector.mjs";

// Ascended Heroes' real production numbers (dry-run artifact, 2026-07-16).
const OPENING_EXPERIENCE = {
  status: "available",
  cohort: { version: "public_analytics_policy_v1_era_gated", eligibleSetCount: 21 },
  rosterDesirability: { score: 95.4809, rank: 1, cohortSize: 21, tier: "S" },
  dualPathDepth: {
    rawValue: 0.27143,
    displayPercent: 27.1,
    rank: 14,
    cohortSize: 21,
    subjectsWithMultiplePaths: 18,
    modeledSubjectCount: 24,
  },
  collectorAppeal: { score: 96.0942, rank: 1, cohortSize: 21, tier: "S", version: "collector_appeal_ca7_v1" },
  chaseAppeal: { score: 92.4, rank: 2, cohortSize: 21, tier: "S" },
  topSubjects: [
    {
      subjectName: "Gengar",
      demandShare: 0.181,
      accessiblePath: {
        canonicalCardId: "card-gengar-dr",
        cardName: "Gengar ex",
        cardNumber: "104",
        rarity: "Double Rare",
        imageUrl: "https://img/gengar-dr.png",
        modeledProbability: 0.005236,
        impliedOdds: 191,
      },
      elitePath: {
        canonicalCardId: "card-gengar-sir",
        cardName: "Gengar ex",
        cardNumber: "215",
        rarity: "Special Illustration Rare",
        imageUrl: "https://img/gengar-sir.png",
        modeledProbability: 0.000652,
        impliedOdds: 1533,
      },
    },
  ],
  coverage: { status: "available", reasons: [], pullModelAvailable: true },
};

test("presentation formats the canonical scores on their honest scales", () => {
  const model = selectOpeningExperiencePresentation(OPENING_EXPERIENCE);

  assert.equal(model.available, true);
  assert.equal(model.collectorAppeal.scoreLabel, "96.1");
  assert.equal(model.collectorAppeal.rankLabel, "#1 of 21");
  assert.equal(model.rosterDesirability.scoreLabel, "95.5");
  assert.equal(model.chaseAppeal.scoreLabel, "92.4");
  assert.equal(model.cohortSize, 21);
});

test("Dual-Path Depth is a percentage of its raw structural scale — never a rescale, never a tier", () => {
  const model = selectOpeningExperiencePresentation(OPENING_EXPERIENCE);

  assert.equal(model.dualPathDepth.displayLabel, "27.1%");
  assert.equal(model.dualPathDepth.rankLabel, "#14 of 21");
  assert.equal(model.dualPathDepth.subjectsWithMultiplePaths, 18);
  assert.ok(!("tier" in model.dualPathDepth), "P must not carry a tier");
  assert.ok(!("scoreLabel" in model.dualPathDepth), "P must not present as a 0-100 grade");
});

test("subject paths identify specific printings with backend-provided odds", () => {
  const model = selectOpeningExperiencePresentation(OPENING_EXPERIENCE);
  const [gengar] = model.topSubjects;

  assert.equal(gengar.accessiblePath.canonicalCardId, "card-gengar-dr");
  assert.equal(gengar.accessiblePath.cardNumber, "104");
  assert.equal(gengar.accessiblePath.impliedOddsLabel, "1 in 191");
  assert.equal(gengar.elitePath.canonicalCardId, "card-gengar-sir");
  assert.equal(gengar.elitePath.rarity, "Special Illustration Rare");
  assert.equal(gengar.elitePath.impliedOddsLabel, "1 in 1,533");
});

test("a missing or unavailable contract renders unavailable — nulls never become zeros", () => {
  for (const input of [null, undefined, {}, { status: "unavailable", collectorAppeal: { score: null } }]) {
    const model = selectOpeningExperiencePresentation(input);
    assert.equal(model.available, false);
    assert.equal(model.collectorAppeal.score, null);
    assert.equal(model.collectorAppeal.scoreLabel, null);
    assert.equal(model.dualPathDepth.displayLabel, null);
  }
});

test("unavailable reasons pass through from backend coverage", () => {
  const model = selectOpeningExperiencePresentation({
    status: "unavailable",
    coverage: { status: "unavailable", reasons: ["dual_path_depth_unavailable_no_pull_model"] },
  });
  assert.deepEqual(model.unavailableReasons, ["dual_path_depth_unavailable_no_pull_model"]);
});

// ---------------------------------------------------------------------------
// Collector Appeal impact
// ---------------------------------------------------------------------------

const RIP = {
  score: 82.2094,
  rank: 1,
  cohortSize: 21,
  components: {
    desirability: { score: 96.0942, weight: 0.1, contribution: 9.6094, rank: 1, cohortSize: 21 },
  },
};
const RIP_CORE = { score: 83.11, rank: 2, cohortSize: 21 };

test("impact strip model reads the DIRECT backend contribution, not full RIP minus RIP Core", () => {
  const impact = selectCollectorAppealImpact(RIP, RIP_CORE);

  assert.equal(impact.weightLabel, "10%");
  assert.equal(impact.contributionLabel, "9.6 pts");
  assert.equal(impact.finalRip.scoreLabel, "82.2");
  assert.equal(impact.finalRip.rankLabel, "#1 of 21");
  assert.equal(impact.ripCore.scoreLabel, "83.1");
  assert.equal(impact.ripCore.rankLabel, "#2 of 21");
  // RIP Core is renormalized: the naive subtraction (82.2 - 83.1 = -0.9) is
  // NOT the contribution, and the model must not equal it.
  const naive = RIP.score - RIP_CORE.score;
  assert.notEqual(impact.contributionLabel, `${naive.toFixed(1)} pts`);
});

test("rank effect compares RIP Core rank with final RIP rank", () => {
  const impact = selectCollectorAppealImpact(RIP, RIP_CORE);
  assert.equal(impact.rankEffect, 1);
  assert.match(impact.rankEffectLabel, /\+1 vs RIP Core/);

  const unchanged = selectCollectorAppealImpact({ ...RIP, rank: 2 }, RIP_CORE);
  assert.equal(unchanged.rankEffect, 0);
  assert.match(unchanged.rankEffectLabel, /No rank change/);
});

test("impact model is null when neither canonical object carries a score", () => {
  assert.equal(selectCollectorAppealImpact({}, {}), null);
  assert.equal(selectCollectorAppealImpact(null, undefined), null);
});

test("source-level guard: the selector computes nothing the backend owns", () => {
  const source = readFileSync(
    fileURLToPath(new URL("./openingExperienceSelector.mjs", import.meta.url)),
    "utf8"
  );
  const code = source
    .split("\n")
    .filter((line) => !line.trim().startsWith("//") && !line.trim().startsWith("*"))
    .join("\n");
  // No CA7, no lambda, no weight arithmetic, no rank computation.
  assert.ok(!code.includes("0.5"), "the CA7 lambda must not appear");
  assert.ok(!code.includes("0.58"), "RIP weights must not appear");
  assert.ok(!/score\s*\*\s*/.test(code.replace("demandShare * 100", "")), "no score arithmetic beyond display formatting");
  assert.ok(!code.includes(".sort("), "no ranking in the frontend");
  // No legacy fallbacks.
  for (const banned of ["pack_score", "relative_pack_score", "collectorAppealScore", "opening_desirability_score"]) {
    assert.ok(!code.includes(banned), `selector must not read ${banned}`);
  }
});
