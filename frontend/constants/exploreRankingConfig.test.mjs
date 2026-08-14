import test from "node:test";
import assert from "node:assert/strict";

import {
  EXPLORE_RANKING_MODES,
  SCORE_KIND_INDEX,
  SCORE_KIND_PUBLIC,
  SCORE_KIND_RATIO,
  formatModeScore,
  getRankForMode,
  getRankedSetCountField,
  getRankedSetCountForMode,
  getScoreField,
  getScoreForMode,
  getScoreKind,
  isPublicScoreMode,
} from "./exploreRankingConfig.mjs";

const TARGET = {
  // CANONICAL. The public "RIP SCORE" and "FINANCIAL RIP" columns read these.
  // `score` and `relativeScore` differ deliberately so an assertion can tell
  // which layer a column resolved.
  overallRipV8: { score: 29.07, relativeScore: 82.4, rank: 4, tier: "A", cohortSize: 21 },
  financialRipV3: { score: 22.32, relativeScore: 61.8, rank: 12, tier: "B", cohortSize: 21 },
  // LEGACY, still served for audit consumers: Overall RIP v4 and Financial RIP
  // V2. Deliberately given DIFFERENT numbers so a regression that reads them
  // under a canonical label fails loudly instead of coincidentally matching.
  rip: {
    score: 88.8,
    relativeScore: 12.3,
    rank: 19,
    tier: "F",
    cohortSize: 21,
    financialRip: {
      components: {
        profit: { score: 40.1, rank: 6, tier: "B", cohortSize: 21 },
        safety: { score: 41.2, rank: 7, tier: "B", cohortSize: 21 },
        stability: { score: 42.3, rank: 8, tier: "C", cohortSize: 21 },
      },
    },
  },
  ripCore: { score: 77.7, relativeScore: 15.5, rank: 18, tier: "F", cohortSize: 21 },
  universalSetDesirability: { score: 95.5, rank: 1, rankedSetCount: 135 },
  mean_value_to_cost_ratio: 1.23,
  mean_value_to_cost_rank: 3,
  p99_value_to_cost_ratio: 18.4,
  p99_value_to_cost_rank: 2,
};

// --- The canonical public columns -------------------------------------------

test("the two canonical modes read the PUBLIC relative score and nothing else", () => {
  assert.equal(getScoreField("overall"), "overallRipV8.relativeScore");
  assert.equal(getScoreField("financial"), "financialRipV3.relativeScore");
  assert.equal(getScoreForMode(TARGET, "overall"), 82.4);
  assert.equal(getScoreForMode(TARGET, "financial"), 61.8);
  assert.equal(getRankForMode(TARGET, "overall"), 4);
  assert.equal(getRankForMode(TARGET, "financial"), 12);
});

test("no mode exposes a fixed-anchor model score field", () => {
  // The absolute is a real model number and stays in the payload, but the
  // ranking config must not offer it: a config that hands a surface both
  // layers is a config that invites the surface to pick the wrong one, which
  // is how the same metric rendered on two scales.
  for (const [id, mode] of Object.entries(EXPLORE_RANKING_MODES)) {
    const serialized = JSON.stringify(mode);
    assert.equal(/absoluteScoreField/.test(serialized), false, `${id} must not expose an absolute field`);
    assert.equal(/relativeScoreField/.test(serialized), false, `${id} must not expose a rival relative field`);
    assert.equal(/\.absoluteScore/.test(serialized), false, `${id} must not point at an absoluteScore path`);
  }
  assert.equal(getScoreField("overall").endsWith(".score"), false);
  assert.equal(getScoreField("financial").endsWith(".score"), false);
});

test("the canonical modes never read a legacy object", () => {
  for (const mode of ["overall", "financial"]) {
    const field = getScoreField(mode);
    assert.equal(field.startsWith("rip."), false, `${mode} must not read Overall RIP v4`);
    assert.equal(field.startsWith("ripCore"), false, `${mode} must not read Financial RIP V2`);
    assert.equal(/pack_score|pack_rank|relative_pack_score/.test(field), false);
  }
});

// --- Retired legacy V2 lenses -----------------------------------------------

test("the Financial RIP V2 pillar lenses are retired as public ranking modes", () => {
  for (const retired of ["profit", "safety", "stability"]) {
    assert.equal(retired in EXPLORE_RANKING_MODES, false, `${retired} must no longer be a public lens`);
  }
});

test("no surviving mode reads Financial RIP V2 pillars", () => {
  for (const [id, mode] of Object.entries(EXPLORE_RANKING_MODES)) {
    const field = mode.publicScoreField || mode.scoreField || "";
    assert.equal(
      field.includes("rip.financialRip.components"),
      false,
      `${id} must not rank on a retired V2 pillar`
    );
  }
});

// --- Every column declares what kind of number it holds ----------------------

test("every mode declares a score kind", () => {
  for (const [id, mode] of Object.entries(EXPLORE_RANKING_MODES)) {
    assert.ok(
      [SCORE_KIND_PUBLIC, SCORE_KIND_INDEX, SCORE_KIND_RATIO].includes(mode.scoreKind),
      `${id} must declare a scoreKind`
    );
    assert.ok(mode.publicScoreField || mode.scoreField, `${id} must declare exactly one score field`);
  }
});

test("only the three canonical public metrics take the public-score treatment", () => {
  const publicModes = Object.values(EXPLORE_RANKING_MODES)
    .filter((mode) => mode.scoreKind === SCORE_KIND_PUBLIC)
    .map((mode) => mode.id)
    .sort();
  assert.deepEqual(publicModes, ["financial", "overall"]);
  assert.equal(isPublicScoreMode("overall"), true);
  assert.equal(isPublicScoreMode("financial"), true);
  assert.equal(isPublicScoreMode("desirability"), false);
  assert.equal(isPublicScoreMode("averageReturn"), false);
});

test("a ratio column can never be formatted as a 0-100 score", () => {
  assert.equal(getScoreKind("averageReturn"), SCORE_KIND_RATIO);
  assert.equal(getScoreKind("jackpotUpside"), SCORE_KIND_RATIO);
  assert.equal(formatModeScore(getScoreForMode(TARGET, "averageReturn"), getScoreKind("averageReturn")), "1.2x");
  assert.equal(formatModeScore(getScoreForMode(TARGET, "jackpotUpside"), getScoreKind("jackpotUpside")), "18.4x");
  // And a public score is never suffixed with an x.
  assert.equal(formatModeScore(getScoreForMode(TARGET, "overall"), getScoreKind("overall")), "82.4");
});

test("public scores format to exactly one decimal", () => {
  assert.equal(formatModeScore(100, SCORE_KIND_PUBLIC), "100.0");
  assert.equal(formatModeScore(0, SCORE_KIND_PUBLIC), "0.0");
  assert.equal(formatModeScore(88, SCORE_KIND_PUBLIC), "88.0");
  assert.equal(formatModeScore(null, SCORE_KIND_PUBLIC), "—");
});

// --- Set Desirability stays its own concept ---------------------------------

test("Set Desirability is a distinct index against its own all-set cohort", () => {
  const mode = EXPLORE_RANKING_MODES.desirability;
  assert.equal(mode.label, "Set Desirability");
  assert.equal(mode.scoreLabel, "SET DESIRABILITY");
  assert.equal(mode.scoreKind, SCORE_KIND_INDEX, "it is not one of the three canonical public metrics");
  assert.equal(getScoreForMode(TARGET, "desirability"), 95.5);
  // Its OWN denominator (135 scored sets), never the opening cohort's 21.
  assert.equal(getRankedSetCountForMode(TARGET, "desirability"), 135);
  assert.notEqual(getRankedSetCountForMode(TARGET, "desirability"), getRankedSetCountForMode(TARGET, "overall"));
  // And it is never presented as Collector Appeal.
  assert.equal(/Collector Appeal/.test(mode.label), false);
  assert.equal(/Collector Appeal/.test(mode.scoreLabel), false);
});

// --- Vocabulary -------------------------------------------------------------

test("no mode publishes retired public vocabulary", () => {
  const forbidden = [
    /God Pull/i,
    /GOD PULL/,
    /RIP Score/,
    /Relative RIP Index/,
    /Financial Quality/,
    /Opening Desirability/,
  ];
  for (const [id, mode] of Object.entries(EXPLORE_RANKING_MODES)) {
    const copy = [mode.label, mode.title, mode.subtitle, mode.tooltip, mode.scoreLabel, mode.tierLabel, mode.description]
      .filter(Boolean)
      .join(" | ");
    for (const pattern of forbidden) {
      assert.equal(pattern.test(copy), false, `${id} copy must not contain ${pattern}`);
    }
  }
});

test("the canonical modes are labelled Overall RIP and Financial RIP", () => {
  assert.equal(EXPLORE_RANKING_MODES.overall.scoreLabel, "OVERALL RIP");
  assert.equal(EXPLORE_RANKING_MODES.financial.scoreLabel, "FINANCIAL RIP");
  assert.equal(EXPLORE_RANKING_MODES.financial.label, "Financial RIP");
});

test("Jackpot Upside is the only name for the top-1% ranking lens", () => {
  const mode = EXPLORE_RANKING_MODES.jackpotUpside;
  assert.equal(mode.label, "Jackpot Upside");
  assert.equal(mode.scoreLabel, "JACKPOT UPSIDE");
  assert.equal("godPullUpside" in EXPLORE_RANKING_MODES, false);
  assert.equal(getScoreField("jackpotUpside"), "p99_value_to_cost_ratio");
});

// --- Denominators and null-safety -------------------------------------------

test("ranked-set count reads each mode's own cohort denominator", () => {
  assert.equal(getRankedSetCountField("overall"), "overallRipV8.cohortSize");
  assert.equal(getRankedSetCountForMode(TARGET, "overall"), 21);
  assert.equal(getRankedSetCountForMode(TARGET, "financial"), 21);
  assert.equal(getRankedSetCountForMode(TARGET, "desirability"), 135);
});

test("ratio-only modes expose no ranked-set count field", () => {
  for (const mode of ["averageReturn", "jackpotUpside"]) {
    assert.equal(getRankedSetCountField(mode), null);
    assert.equal(getRankedSetCountForMode(TARGET, mode), null);
  }
});

test("null-safe getters: missing objects never throw and return null", () => {
  const empty = {};
  for (const mode of Object.keys(EXPLORE_RANKING_MODES)) {
    assert.equal(getScoreForMode(empty, mode), null);
    assert.equal(getRankForMode(empty, mode), null);
    assert.equal(getRankedSetCountForMode(empty, mode), null);
  }
});

test("a payload carrying ONLY the model score renders no public score", () => {
  // The exact stale-snapshot shape. It must not fall back to the absolute.
  const absoluteOnly = { overallRipV8: { score: 30.0, rank: 2, cohortSize: 21 } };
  assert.equal(getScoreForMode(absoluteOnly, "overall"), null);
  assert.equal(formatModeScore(getScoreForMode(absoluteOnly, "overall"), getScoreKind("overall")), "—");
  // Rank still resolves — it is a separate, still-valid backend field.
  assert.equal(getRankForMode(absoluteOnly, "overall"), 2);
});

test("an unknown mode falls back to the canonical overall mode", () => {
  assert.equal(getScoreForMode(TARGET, "does-not-exist"), 82.4);
  assert.equal(getScoreKind("does-not-exist"), SCORE_KIND_PUBLIC);
});
