import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import {
  SET_DESIRABILITY_EXPLANATION,
  selectOpeningExperiencePresentation,
  selectRipDesirabilityBreakdown,
  selectSetDesirabilityPresentation,
} from "./openingExperienceSelector.mjs";

// Ascended Heroes' real production numbers (verified live, 2026-07-16).
const UNIVERSAL = {
  score: 95.4809,
  rank: 1,
  rankedSetCount: 135,
  percentile: 100.0,
  version: "universal_set_desirability_v3",
  components: {
    chase_subject_strength: 86.6628,
    chase_subject_depth: 100.0,
    favorite_hit_coverage: 99.8113,
  },
  componentWeights: {
    chase_subject_strength: 0.333333,
    chase_subject_depth: 0.277778,
    favorite_hit_coverage: 0.388889,
  },
  weightsLabel: "Reasoned defaults, not empirically fitted values.",
  effectiveSubjectCount: 12.4,
  distinctEligibleSubjectCount: 24,
  top1Share: 0.181,
  top3Share: 0.402,
  topSubjects: [
    {
      subjectName: "Gengar",
      subjectDemand: 98.2,
      cardCount: 3,
      representativeCardName: "Gengar ex",
      bestRarityBucket: "special_illustration_rare",
    },
  ],
  coverage: { status: "full", reasons: [], scoredHitEligibleShare: 1.0 },
};

const OPENING_EXPERIENCE = {
  status: "available",
  cohort: { version: "public_analytics_policy_v1_era_gated", eligibleSetCount: 21 },
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
  coverage: { status: "available", reasons: [], pullModelAvailable: true, scope: "simulation_opening_experience" },
};

// ---------------------------------------------------------------------------
// Set Desirability
// ---------------------------------------------------------------------------

test("Set Desirability exposes score, all-set rank, cohort size and percentile", () => {
  const model = selectSetDesirabilityPresentation(UNIVERSAL);

  assert.equal(model.available, true);
  assert.equal(model.scoreLabel, "95.5");
  assert.equal(model.rankLabel, "#1 of 135");
  assert.equal(model.rankedSetCount, 135);
  assert.equal(model.percentileLabel, "100.0%");
});

test("Set Desirability exposes the three named components", () => {
  const model = selectSetDesirabilityPresentation(UNIVERSAL);
  assert.deepEqual(
    model.components.map((row) => row.label),
    ["Chase Subject Strength", "Chase Subject Depth", "Favorite Hit Coverage"]
  );
  assert.deepEqual(
    model.components.map((row) => row.scoreLabel),
    ["86.7", "100.0", "99.8"]
  );
});

test("Set Desirability exposes concentration diagnostics and top subjects", () => {
  const model = selectSetDesirabilityPresentation(UNIVERSAL);
  assert.equal(model.effectiveSubjectCountLabel, "12.40");
  assert.equal(model.distinctEligibleSubjectCount, 24);
  assert.equal(model.top1ShareLabel, "18.1%");
  assert.equal(model.top3ShareLabel, "40.2%");
  assert.equal(model.topSubjects[0].subjectName, "Gengar");
  assert.equal(model.topSubjects[0].subjectDemandLabel, "98.2");
});

test("Set Desirability renders with NO simulation, NO CA7 and NO Financial RIP", () => {
  // The regression: the universal score was hidden whenever the pull model
  // could not be read, even though the backend had already computed it.
  const model = selectSetDesirabilityPresentation(UNIVERSAL);
  assert.equal(model.available, true);
  assert.equal(model.scoreLabel, "95.5");

  // And the Simulation Opening Experience being unavailable changes nothing.
  const opening = selectOpeningExperiencePresentation({
    status: "unavailable",
    coverage: { status: "unavailable", reasons: ["dual_path_depth_unavailable_no_pull_model"] },
  });
  assert.equal(opening.available, false);
  assert.equal(model.available, true, "Set Desirability must not depend on CA7");
});

test("Set Desirability is unavailable only when its OWN coverage is not full", () => {
  const partial = selectSetDesirabilityPresentation({
    ...UNIVERSAL,
    coverage: { status: "unavailable", reasons: ["no_eligible_pokemon_subjects"] },
  });
  assert.equal(partial.available, false);
  assert.deepEqual(partial.unavailableReasons, ["no_eligible_pokemon_subjects"]);
});

test("Set Desirability nulls never become zeros", () => {
  for (const input of [null, undefined, {}, { score: null }]) {
    const model = selectSetDesirabilityPresentation(input);
    assert.equal(model.available, false);
    assert.equal(model.score, null);
    assert.equal(model.scoreLabel, null);
    assert.equal(model.rankLabel, null);
  }
});

test("Set Desirability carries the price-independence explanation", () => {
  const model = selectSetDesirabilityPresentation(UNIVERSAL);
  assert.match(model.explanation, /does not use card prices/);
  assert.match(SET_DESIRABILITY_EXPLANATION, /popularity and depth/);
});

// ---------------------------------------------------------------------------
// Simulation Opening Experience (CA7-scoped)
// ---------------------------------------------------------------------------

test("Opening Experience formats the CA7 scores on their honest scales", () => {
  const model = selectOpeningExperiencePresentation(OPENING_EXPERIENCE);

  assert.equal(model.available, true);
  assert.equal(model.collectorAppeal.scoreLabel, "96.1");
  assert.equal(model.collectorAppeal.rankLabel, "#1 of 21");
  assert.equal(model.chaseAppeal.scoreLabel, "92.4");
  assert.equal(model.cohortSize, 21);
});

test("Opening Experience no longer carries roster desirability", () => {
  const model = selectOpeningExperiencePresentation(OPENING_EXPERIENCE);
  assert.ok(
    !("rosterDesirability" in model),
    "roster desirability moved to the Set Desirability contract"
  );
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
  assert.equal(gengar.accessiblePath.impliedOddsLabel, "1 in 191");
  assert.equal(gengar.elitePath.rarity, "Special Illustration Rare");
  assert.equal(gengar.elitePath.impliedOddsLabel, "1 in 1,533");
});

test("a missing or unavailable CA7 contract renders unavailable — nulls never become zeros", () => {
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
// RIP breakdown: Financial RIP, Opening Desirability (CA7), Overall RIP
// Overall RIP = 0.90 * Financial RIP + 0.10 * CA7 (no cap, no adjustment).
// ---------------------------------------------------------------------------

const RIP_CORE = { score: 22.3155, relativeScore: 83.7, rank: 4, cohortSize: 21, tier: "A" };
const RIP_OPENING_EXPERIENCE = {
  collectorAppeal: { score: 89.8659, rank: 3, cohortSize: 21, tier: "A" },
};
const RIP = {
  score: 29.0705, // 0.9*22.3155 + 0.1*89.8659
  relativeScore: 98.4,
  rank: 2,
  cohortSize: 21,
  tier: "S",
  version: "overall_rip_v4_90_financial_10_ca7",
  financialRip: { score: 22.3155 },
  openingDesirability: { score: 89.8659, weight: 0.1, contribution: 8.98659 },
  components: {
    financialRip: { score: 22.3155, weight: 0.9, contribution: 20.08395 },
    openingDesirability: { score: 89.8659, weight: 0.1, contribution: 8.98659 },
  },
  effectiveWeights: { profit: 0.54, safety: 0.225, stability: 0.135, opening_desirability: 0.1 },
};

test("breakdown shows Financial RIP, Opening Desirability and Overall RIP", () => {
  const model = selectRipDesirabilityBreakdown(RIP, RIP_CORE, UNIVERSAL, RIP_OPENING_EXPERIENCE);

  assert.equal(model.financialRip.scoreLabel, "22.3");
  assert.equal(model.openingDesirability.scoreLabel, "89.9");
  assert.equal(model.openingDesirability.rankLabel, "#3 of 21");
  assert.equal(model.setDesirability.scoreLabel, "95.5");
  assert.equal(model.setDesirability.rankLabel, "#1 of 135");
  assert.equal(model.overallRip.scoreLabel, "29.1");
});

test("breakdown states the 60/25/15 financial weights", () => {
  const model = selectRipDesirabilityBreakdown(RIP, RIP_CORE, UNIVERSAL, RIP_OPENING_EXPERIENCE);
  assert.equal(model.financialRip.weightsLabel, "Profit 60% · Safety 25% · Stability 15%");
});

test("Overall RIP is 90% Financial + 10% CA7, contributions read from the backend", () => {
  const model = selectRipDesirabilityBreakdown(RIP, RIP_CORE, UNIVERSAL, RIP_OPENING_EXPERIENCE);
  assert.equal(model.financialRip.weightLabel, "90%");
  assert.equal(model.openingDesirability.weightLabel, "10%");
  assert.ok(model.financialRip.contributionLabel.includes("20.1"));
  assert.ok(model.openingDesirability.contributionLabel.includes("9.0"));
  // No cap and no additive adjustment anywhere in the model.
  assert.ok(!("desirabilityAdjustment" in model));
});

test("breakdown exposes the effective final weights", () => {
  const model = selectRipDesirabilityBreakdown(RIP, RIP_CORE, UNIVERSAL, RIP_OPENING_EXPERIENCE);
  const byLabel = Object.fromEntries(model.effectiveWeights.map((w) => [w.label, w.valueLabel]));
  assert.equal(byLabel.Profit, "54.0%");
  assert.equal(byLabel.Safety, "22.5%");
  assert.equal(byLabel.Stability, "13.5%");
  assert.equal(byLabel["Opening Desirability"], "10.0%");
});

test("missing CA7 makes Overall RIP unavailable but keeps Financial + Set Desirability", () => {
  const model = selectRipDesirabilityBreakdown(
    { score: null, financialRip: { score: 22.3155 }, statusReason: "no ca7" },
    RIP_CORE,
    UNIVERSAL,
    { collectorAppeal: { score: null } }
  );
  assert.equal(model.overallRip.scoreLabel, null);
  assert.equal(model.openingDesirability.scoreLabel, null);
  assert.ok(model.openingDesirability.unavailableReason);
  assert.equal(model.financialRip.scoreLabel, "22.3");
  assert.equal(model.setDesirability.scoreLabel, "95.5");
});

test("contribution math uses ABSOLUTE scores; relative is a separate standardization step", () => {
  const model = selectRipDesirabilityBreakdown(RIP, RIP_CORE, UNIVERSAL, RIP_OPENING_EXPERIENCE);

  // Contribution math is on the absolute (model) scores, never the relatives.
  assert.equal(model.financialRip.score, 22.3155);
  assert.equal(model.overallRip.score, 29.0705);
  assert.ok(model.financialRip.contributionLabel.includes("20.1")); // 22.3155 * 0.9
  // The public relative scores are exposed as a distinct standardization result.
  assert.equal(model.financialRip.relativeScore, 83.7);
  assert.equal(model.financialRip.relativeScoreLabel, "83.7");
  assert.equal(model.overallRip.relativeScore, 98.4);
  assert.equal(model.overallRip.relativeScoreLabel, "98.4");
  assert.ok(model.overallRip.standardizationNote.includes("98.4"));
  assert.ok(model.overallRip.standardizationNote.toLowerCase().includes("standardized"));
  // The relative public score is NOT the contribution sum (proves no blending).
  assert.notEqual(model.overallRip.relativeScore, model.overallRip.score);
});

test("breakdown never presents Set Desirability as a weighted RIP pillar", () => {
  const model = selectRipDesirabilityBreakdown(RIP, RIP_CORE, UNIVERSAL, RIP_OPENING_EXPERIENCE);
  assert.ok(!("weight" in model.setDesirability), "Set Desirability is a supporting input, not a weight");
  assert.ok(!("contribution" in model.setDesirability));
});

test("breakdown is null when nothing carries a score", () => {
  assert.equal(selectRipDesirabilityBreakdown({}, {}, {}), null);
  assert.equal(selectRipDesirabilityBreakdown(null, undefined, null), null);
});

// ---------------------------------------------------------------------------
// Source guards
// ---------------------------------------------------------------------------

test("source-level guard: the selector computes nothing the backend owns", () => {
  const source = readFileSync(
    fileURLToPath(new URL("./openingExperienceSelector.mjs", import.meta.url)),
    "utf8"
  );
  const code = source
    .split("\n")
    .filter((line) => !line.trim().startsWith("//") && !line.trim().startsWith("*"))
    .join("\n");
  assert.ok(!code.includes("0.58"), "retired RIP weights must not appear");
  assert.ok(!code.includes("0.60 *"), "financial weights must not be applied here");
  assert.ok(!code.includes(".sort("), "no ranking in the frontend");
  for (const banned of ["pack_score", "relative_pack_score", "collectorAppealScore", "opening_desirability_score"]) {
    assert.ok(!code.includes(banned), `selector must not read ${banned}`);
  }
});

test("source-level guard: the legacy CA7 impact strip is gone", () => {
  const source = readFileSync(
    fileURLToPath(new URL("./openingExperienceSelector.mjs", import.meta.url)),
    "utf8"
  );
  assert.ok(
    !source.includes("selectCollectorAppealImpact"),
    "the CA7 impact strip presented CA7 as the authoritative 10% RIP pillar"
  );
});
