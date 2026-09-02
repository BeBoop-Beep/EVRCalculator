// THE CROSS-SURFACE PUBLIC METRIC CONTRACT.
//
// One concept -> one canonical public field -> one name -> one public scale ->
// one definition -> identical value everywhere.
//
// WHAT THIS EXISTS TO CATCH
// -------------------------
// A set page that rendered Collector Appeal as 53.2 in its "Why It Ranks" block
// and 95.9 in the RIP Summary a few centimetres above it. Both numbers were
// correct and both came from the same canonical backend contract; the surfaces
// simply chose different fields off it. Financial RIP did the same, under two
// different names ("Financial Quality" and "Financial RIP").
//
// No single-surface test could see that, because each surface was individually
// self-consistent. So this file drives EVERY public selector from ONE fixture in
// which the absolute and the relative deliberately differ, and asserts they all
// land on the same number.
//
// It also pins the outcome-metric definitions (EV = mean, Typical Opening = P50,
// Strong Upside = P95 threshold, Jackpot Upside = top-1% threshold) and guards
// the retired vocabulary.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { PUBLIC_SCORE_SCALE_NOTE, readCanonicalBlock, resolveCanonicalRipV7 } from "./canonicalRipV7.mjs";
import { selectRipHeroScoreMode } from "./ripHeroScoreMode.mjs";
import { buildRipDrivers } from "./ripDrivers.mjs";
import { resolveCanonicalFinancialRip, selectFinancialRipV3Breakdown } from "./financialRipV3Selector.mjs";
import { selectCollectorAppealBreakdown } from "./collectorAppealBreakdownSelector.mjs";
import { selectLandingHeroEntries } from "../../lib/landing/landingHeroSpotlight.mjs";
import {
  EXPLORE_RANKING_MODES,
  formatModeScore,
  getScoreForMode,
  getScoreKind,
} from "../../constants/exploreRankingConfig.mjs";
import { selectTrendScores } from "./trendScoresSelector.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
// The repo has mixed CRLF/LF; normalise before any multi-line source assertion.
const readSource = (relative) =>
  fs.readFileSync(path.resolve(here, relative), "utf8").replace(/\r\n/g, "\n");

// --- THE fixture -------------------------------------------------------------
//
// Every metric's absolute and relative differ by a wide margin, so a surface
// reading the wrong layer cannot coincidentally produce the right answer. The
// Collector Appeal pair is literally the reported defect: 53.2 vs 95.9.

const PUBLIC_RIP_SCORE = 88.4;
const PUBLIC_FINANCIAL_RIP = 71.9;
const PUBLIC_COLLECTOR_APPEAL = 95.9;

const MODEL_RIP_SCORE = 40.3;
const MODEL_FINANCIAL_RIP = 39.1;
const MODEL_COLLECTOR_APPEAL = 53.2;

const COHORT = 22;

// The public Set RIP V1 block — the homepage's ranking authority. Set to
// disagree with Overall RIP's rank/tier so a surface reading the wrong
// metric cannot coincidentally produce the right answer.
const PUBLIC_SET_RIP_SCORE = 76.1;
const PUBLIC_SET_RIP_RANK = 5;
const PUBLIC_SET_RIP_TIER = "B";
const SET_RIP_V1 = {
  score: PUBLIC_SET_RIP_SCORE,
  rank: PUBLIC_SET_RIP_RANK,
  tier: PUBLIC_SET_RIP_TIER,
  cohortSize: COHORT,
  rankable: true,
};

function financialComponent(score, relativeScore, rank, raw) {
  return { score, absoluteScore: score, relativeScore, rank, cohortSize: COHORT, rankedSetCount: COHORT, tier: "A", raw };
}

const CONTRACT = {
  contractVersion: "public_rip_contract_v8",
  overallRip: {
    score: MODEL_RIP_SCORE,
    absoluteScore: MODEL_RIP_SCORE,
    relativeScore: PUBLIC_RIP_SCORE,
    rank: 2,
    rankedSetCount: COHORT,
    tier: "S",
  },
  financialRip: {
    status: "ready",
    score: MODEL_FINANCIAL_RIP,
    absoluteScore: MODEL_FINANCIAL_RIP,
    relativeScore: PUBLIC_FINANCIAL_RIP,
    rank: 3,
    rankedSetCount: COHORT,
    tier: "A",
    components: {
      true_win_frequency: financialComponent(31.2, 74.5, 5, { trueWinProbability: 0.212, packCost: 4.99 }),
      typical_retention: financialComponent(28.1, 63.0, 8, { typicalPackValue: 2.4, typicalRetentionRatio: 0.48, packCost: 4.99 }),
      loss_resilience: financialComponent(35.0, 79.0, 4, { averageRetentionGivenLoss: 0.41, softLossShareGivenLoss: 0.2, averageLosingReturnValue: 2.05, hardLossProbability: 0.5 }),
      realistic_upside: financialComponent(55.4, 91.2, 2, {
        p95ThresholdValue: 14.25,
        p95ThresholdRatio: 2.856,
        realisticTailMeanValue: 26.8,
        realisticTailMeanRatio: 5.371,
      }),
      jackpot_upside: financialComponent(61.0, 88.7, 3, {
        p99ThresholdValue: 61.9,
        p99ThresholdRatio: 12.404,
        jackpotTailMeanValue: 140.5,
        jackpotTailMeanRatio: 28.156,
        jackpotValueShare: 0.19,
      }),
      base_economic_efficiency: financialComponent(39.8, 70.1, 6, {
        totalRtpRatio: 0.824,
        baseRtpExcludingTop1Pct: 0.612,
        jackpotValueShare: 0.19,
      }),
    },
    depthAndRobustness: { status: "ready", effectiveChaseCount: 4.2, top1EvShare: 0.31, jackpotValueShare: 0.19 },
  },
  collectorAppeal: {
    score: MODEL_COLLECTOR_APPEAL,
    absoluteScore: MODEL_COLLECTOR_APPEAL,
    relativeScore: PUBLIC_COLLECTOR_APPEAL,
    rank: 1,
    rankedSetCount: COHORT,
    tier: "S",
    components: {
      rosterDesirability: { score: 84.0, rawValue: 0.84 },
      desirableOutcomeFrequency: { rawValue: 0.19, impliedOddsOneInN: 5.3, eligibleCardCount: 18, eligibleSubjectCount: 7, coveredDemandShare: 0.86 },
      dualPathDepth: { rawValue: 0.42, subjectsWithMultiplePaths: 3 },
    },
    subjectScope: { modeled: ["Pokémon"], notYetModeled: ["Trainer", "Artist"] },
  },
};

// A ranked Explore/landing target: the packaged contract plus the top-level
// objects the leaderboard columns read.
const TARGET = {
  target_type: "set",
  target_id: "set-1",
  name: "Fixture Set",
  publicRipContractV8: CONTRACT,
  overallRipV8: {
    score: MODEL_RIP_SCORE,
    relativeScore: PUBLIC_RIP_SCORE,
    rank: 2,
    cohortSize: COHORT,
    tier: "S",
  },
  financialRipV3: {
    score: MODEL_FINANCIAL_RIP,
    relativeScore: PUBLIC_FINANCIAL_RIP,
    rank: 3,
    cohortSize: COHORT,
    tier: "A",
    status: "ready",
  },
  pack_cost: 4.99,
  mean_value: 3.21,
  median_value: 2.4,
  prob_profit: 0.212,
  // LEGACY, deliberately different, deliberately never rendered.
  rip: { score: 12.0, relativeScore: 11.1, rank: 19, tier: "F", cohortSize: COHORT },
  ripCore: { score: 13.0, relativeScore: 14.4, rank: 20, tier: "F", cohortSize: COHORT },
  pack_score: 55.5,
  relative_pack_score: 66.6,
  pack_rank: 17,
  pack_tier: "D",
  openingDesirability: { collectorAppealScore: 44.4, chaseAppealScore: 33.3 },
  setRipV1: SET_RIP_V1,
};

const CANONICAL = resolveCanonicalRipV7(TARGET);

// =============================================================================
// 1. Same set + same concept = the same public number on every surface.
// =============================================================================

test("RIP Score is one number on every public surface that displays Overall RIP", () => {
  // Home is NOT part of this set: the homepage set leaderboard's ranking
  // authority is Set RIP V1, not Overall RIP (see the dedicated Home/Rankings
  // Set RIP test below) — a set's Overall RIP and Set RIP V1 are deliberately
  // different numbers in this fixture, so a surface reading the wrong one
  // cannot coincidentally pass.
  const readings = {
    // Set page hero + Insights headline.
    hero: selectRipHeroScoreMode({ canonical: CANONICAL }).publicScore,
    // Overview RIP Summary + Insights Summary card.
    summary: readCanonicalBlock(CANONICAL.overall).publicScore,
    // Explore / Rankings leaderboard column.
    explore: getScoreForMode(TARGET, "overall"),
  };
  for (const [surface, value] of Object.entries(readings)) {
    assert.equal(value, PUBLIC_RIP_SCORE, `${surface} must show the canonical public RIP Score`);
    assert.notEqual(value, MODEL_RIP_SCORE, `${surface} must not show the fixed-anchor model score`);
  }
  assert.equal(new Set(Object.values(readings)).size, 1, "every surface must agree");
});

test("Home Set RIP === Rankings Sets lens setRipV1 (score, rank, tier)", () => {
  // The homepage's #1/#2/#3 must be driven by the SAME public setRipV1 block
  // the Rankings "sets" lens reads (projectRankingsClientPublicSetLeaderboard
  // passes target.setRipV1 straight through) — never Overall RIP, never a
  // legacy pack_rank. This fixture's Overall RIP (88.4/rank 2/tier S) and Set
  // RIP V1 (76.1/rank 5/tier B) deliberately disagree, so a homepage reading
  // the wrong metric cannot coincidentally land on the right number.
  const home = selectLandingHeroEntries([TARGET])[0];
  assert.equal(home.score, TARGET.setRipV1.score);
  assert.equal(home.rank, TARGET.setRipV1.rank);
  assert.equal(home.tier, TARGET.setRipV1.tier);
  assert.equal(home.score, PUBLIC_SET_RIP_SCORE);
  assert.equal(home.rank, PUBLIC_SET_RIP_RANK);
  assert.equal(home.tier, PUBLIC_SET_RIP_TIER);
  assert.notEqual(home.score, PUBLIC_RIP_SCORE, "Home must not show Overall RIP's score");
});

test("Financial RIP is one number on every public surface", () => {
  const financial = selectFinancialRipV3Breakdown(resolveCanonicalFinancialRip(CANONICAL));
  const drivers = buildRipDrivers({
    financial: readCanonicalBlock(CANONICAL.financialRip),
    collector: readCanonicalBlock(CANONICAL.collectorAppeal),
    overall: readCanonicalBlock(CANONICAL.overall),
  });
  const driver = drivers.drivers.find((entry) => entry.key === "financial");

  const readings = {
    // Overview RIP Summary + Insights Summary card + Financial RIP breakdown.
    breakdown: financial.publicScore,
    // "Why It Ranks" driver — the surface that used to print the absolute.
    driver: driver.score,
    // Explore / Rankings "FINANCIAL RIP" column.
    explore: getScoreForMode(TARGET, "financial"),
    // Home does NOT read Financial RIP at all any more — the homepage set
    // leaderboard entry carries no financialRipScore field (see the Set RIP
    // authority test above), so it is intentionally excluded here.
  };
  for (const [surface, value] of Object.entries(readings)) {
    assert.equal(value, PUBLIC_FINANCIAL_RIP, `${surface} must show the canonical public Financial RIP`);
    assert.notEqual(value, MODEL_FINANCIAL_RIP, `${surface} must not show the fixed-anchor model score`);
  }
  assert.equal(new Set(Object.values(readings)).size, 1, "every surface must agree");
});

test("Collector Appeal is one number on every public surface — the 53.2 vs 95.9 regression", () => {
  const appeal = selectCollectorAppealBreakdown(CANONICAL);
  const drivers = buildRipDrivers({
    financial: readCanonicalBlock(CANONICAL.financialRip),
    collector: readCanonicalBlock(CANONICAL.collectorAppeal),
    overall: readCanonicalBlock(CANONICAL.overall),
  });
  const driver = drivers.drivers.find((entry) => entry.key === "collector");

  const readings = {
    // Overview RIP Summary + Insights Summary card.
    breakdown: appeal.publicScore,
    // "Why It Ranks" driver — the surface that printed 53.2.
    driver: driver.score,
  };
  for (const [surface, value] of Object.entries(readings)) {
    assert.equal(value, PUBLIC_COLLECTOR_APPEAL, `${surface} must show the canonical public Collector Appeal`);
    assert.notEqual(value, MODEL_COLLECTOR_APPEAL, `${surface} must not show 53.2`);
  }
  assert.equal(new Set(Object.values(readings)).size, 1, "every surface must agree");
});

test("rank, tier and cohort denominator are identical across surfaces too", () => {
  const hero = selectRipHeroScoreMode({ canonical: CANONICAL });
  const summary = readCanonicalBlock(CANONICAL.overall);
  assert.deepEqual(
    [hero.rank, hero.tier, hero.cohortSize],
    [summary.rank, summary.tier, summary.cohortSize]
  );
  assert.equal(hero.rank, 2);
  assert.equal(hero.tier, "S");
  assert.equal(hero.cohortSize, COHORT);
  // Rank and tier come from the canonical block, never from a legacy object.
  assert.notEqual(hero.rank, TARGET.rip.rank);
  assert.notEqual(hero.rank, TARGET.pack_rank);
  assert.notEqual(hero.tier, TARGET.pack_tier);
});

// =============================================================================
// 2. Public consumers cannot read the wrong layer.
// =============================================================================

test("no public selector returns a generic `score` that could mean either layer", () => {
  // The structural defect: `readCanonicalBlock().score` meant the RELATIVE
  // value while `selectFinancialRipV3Breakdown().score` meant the ABSOLUTE one.
  // Neither key exists any more, so a consumer cannot pick wrong by accident.
  assert.equal("score" in readCanonicalBlock(CANONICAL.overall), false);
  assert.equal("score" in selectRipHeroScoreMode({ canonical: CANONICAL }), false);
  assert.equal("score" in selectFinancialRipV3Breakdown(resolveCanonicalFinancialRip(CANONICAL)), false);
  assert.equal("score" in selectCollectorAppealBreakdown(CANONICAL), false);
});

test("the internal model score is still reachable, under an unmistakable name", () => {
  // Not deleted: it is the real model output and audit/Research need it.
  assert.equal(readCanonicalBlock(CANONICAL.overall).modelScore, MODEL_RIP_SCORE);
  assert.equal(selectFinancialRipV3Breakdown(resolveCanonicalFinancialRip(CANONICAL)).modelScore, MODEL_FINANCIAL_RIP);
  assert.equal(selectCollectorAppealBreakdown(CANONICAL).modelScore, MODEL_COLLECTOR_APPEAL);
});

test("ordinary public components never touch absoluteScore themselves", () => {
  // Only the three canonical readers may unwrap the raw contract layer. Any
  // other component reaching for `absoluteScore` is reading around the
  // contract, which is exactly how a second scale got onto a page.
  const ALLOWED = new Set([
    "canonicalRipV7.mjs",
    "financialRipV3Selector.mjs",
    "collectorAppealBreakdownSelector.mjs",
    // TRANSPORT, NOT A SURFACE. This module names `absoluteScore` in a
    // server->client leaf WHITELIST; it never reads the value, formats it, or
    // puts it on screen. It is the module that hands the contract layer to the
    // three readers above, so it has to be able to name the layer's keys. The
    // rule this test enforces is "no component RENDERS a second scale", and a
    // whitelist that carries a key through to a canonical reader is the
    // mechanism that keeps the scales separated rather than a way around it.
    "rankingsClientProjection.mjs",
  ]);
  const offenders = [];
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full);
        continue;
      }
      if (!/\.(jsx?|mjs)$/.test(entry.name)) continue;
      if (entry.name.includes(".test.")) continue;
      if (ALLOWED.has(entry.name)) continue;
      const source = fs.readFileSync(full, "utf8");
      const code = source
        .split("\n")
        .filter((line) => {
          const trimmed = line.trimStart();
          return !trimmed.startsWith("//") && !trimmed.startsWith("*") && !trimmed.startsWith("/*");
        })
        .join("\n");
      if (/\babsoluteScore\b/.test(code)) offenders.push(path.relative(here, full));
    }
  };
  walk(path.resolve(here, ".."));
  walk(path.resolve(here, "../../lib"));
  assert.deepEqual(offenders, [], "these files read absoluteScore outside the canonical readers");
});

test("no public surface renders an exact model weight or contribution share", () => {
  // THE LOCKED PUBLIC CONTRACT: the normal product names what a metric measures
  // and how it ranks. It never publishes the model's composition — because a
  // weight vector over a weighted sum IS the formula, and a contribution in
  // model points is that formula evaluated. Both stay internal.
  //
  // Weights remain valid and unchanged in backend model configuration, in the
  // calculations, in `audit.weights.weights` on the served object, in tests and
  // in comments. This walks the RENDERABLE frontend only.
  //
  // The regression this exists to catch: `formatComponentMeta` appended
  // "· Weight 25%" to every Financial RIP component's rank line, because the
  // public row model carried the weight as a plain field.
  const RENDERED_WEIGHT = [
    /\bWeight \d/, //            "Weight 25%"
    /\bWeight[:=] ?\{/, //       "Weight {value}"
    /\bWeight \$\{/, //          `Weight ${...}`
    /\d\s*% weight\b/i, //       "25% weight"
    /\bweighted \d+\s*%/i, //    "weighted 25%"
    /\bContributes \d/i, //      "Contributes 12 points"
    /\bcontributionPercent\b/,
    /\bweightLabel\b/,
    /\bweightPct\b/,
    /\bformatWeight\b/,
  ];

  const offenders = [];
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "node_modules" || entry.name === ".next") continue;
        walk(full);
        continue;
      }
      if (!/\.(jsx?|mjs)$/.test(entry.name)) continue;
      if (entry.name.includes(".test.")) continue;
      // Prose legitimately names the removed labels while explaining why they
      // were removed, so this reads executable code only.
      const code = fs
        .readFileSync(full, "utf8")
        .replace(/\r\n/g, "\n")
        .split("\n")
        .filter((line) => {
          const trimmed = line.trimStart();
          return !trimmed.startsWith("//") && !trimmed.startsWith("*") && !trimmed.startsWith("/*");
        })
        .join("\n");
      for (const pattern of RENDERED_WEIGHT) {
        if (pattern.test(code)) offenders.push(`${path.relative(here, full)} [${pattern}]`);
      }
    }
  };
  for (const root of ["..", "../../app", "../../lib", "../../constants", "../../hooks"]) {
    const resolved = path.resolve(here, root);
    if (fs.existsSync(resolved)) walk(resolved);
  }
  assert.deepEqual(offenders, [], "these files render an exact weight or contribution share");
});

test("the public metric view models carry no weight a component could render", () => {
  // Belt to the previous test's braces: even if no file renders a weight today,
  // a weight sitting on the object handed to the render layer is one property
  // access away from being rendered tomorrow.
  const financial = selectFinancialRipV3Breakdown(resolveCanonicalFinancialRip(CANONICAL));
  const appeal = selectCollectorAppealBreakdown(CANONICAL);

  for (const [name, view] of [["Financial RIP", financial], ["Collector Appeal", appeal]]) {
    for (const field of ["weight", "weights", "contribution", "contributionPoints"]) {
      assert.equal(field in view, false, `${name} must not expose \`${field}\``);
    }
    for (const row of view.rows || []) {
      for (const field of ["weight", "weights", "contribution", "contributionPoints"]) {
        assert.equal(field in row, false, `${name} / ${row.title || row.key} must not expose \`${field}\``);
      }
    }
  }
});

test("a payload with only the model score renders unavailable, never the model score", () => {
  const absoluteOnly = {
    publicRipContractV8: {
      overallRip: { score: MODEL_RIP_SCORE, absoluteScore: MODEL_RIP_SCORE, rank: 2, tier: "S", rankedSetCount: COHORT },
      financialRip: { status: "ready", score: MODEL_FINANCIAL_RIP, absoluteScore: MODEL_FINANCIAL_RIP, components: CONTRACT.financialRip.components },
      collectorAppeal: { score: MODEL_COLLECTOR_APPEAL, absoluteScore: MODEL_COLLECTOR_APPEAL, components: CONTRACT.collectorAppeal.components },
    },
  };
  const canonical = resolveCanonicalRipV7(absoluteOnly);
  const hero = selectRipHeroScoreMode({ canonical });
  assert.equal(hero.available, false);
  assert.equal(hero.publicScore, null);

  const financial = selectFinancialRipV3Breakdown(resolveCanonicalFinancialRip(canonical));
  assert.equal(financial.publicAvailable, false);
  assert.equal(financial.publicScore, null);
  assert.equal(financial.publicScoreLabel, "—");

  const appeal = selectCollectorAppealBreakdown(canonical);
  assert.equal(appeal.publicAvailable, false);
  assert.equal(appeal.publicScore, null);
  assert.equal(appeal.publicScoreLabel, "—");

  // Home skips the set rather than publishing a differently-scaled number —
  // here that means an absent/unrankable setRipV1, Home's OWN authority.
  assert.deepEqual(selectLandingHeroEntries([{ ...TARGET, publicRipContractV8: absoluteOnly.publicRipContractV8, overallRipV8: {}, financialRipV3: {}, setRipV1: {} }]), []);
});

// =============================================================================
// 3. Legacy contracts can never satisfy a canonical public read.
// =============================================================================

test("a legacy-only payload yields no public score anywhere", () => {
  const legacyOnly = {
    target_type: "set",
    target_id: "legacy",
    name: "Legacy Only",
    rip: TARGET.rip,
    ripCore: TARGET.ripCore,
    overallRipV5: { score: 36.6, relativeScore: 40.0, rank: 5 },
    overallRipV6: { score: 38.2, relativeScore: 41.0, rank: 4 },
    publicRipContractV4: { overallRip: { score: 66.6 } },
    publicRipContractV5: { overallRip: { score: 67.7 } },
    publicRipContractV6: { overallRip: { score: 68.8 } },
    pack_score: 55.5,
    relative_pack_score: 66.6,
    pack_rank: 17,
    openingDesirability: { collectorAppealScore: 44.4 },
  };
  const canonical = resolveCanonicalRipV7(legacyOnly);
  assert.equal(canonical.shape, null);
  assert.equal(selectRipHeroScoreMode({ canonical }).publicScore, null);
  assert.equal(selectFinancialRipV3Breakdown(resolveCanonicalFinancialRip(canonical)).publicScore, null);
  assert.equal(selectCollectorAppealBreakdown(canonical).publicScore, null);
  assert.equal(getScoreForMode(legacyOnly, "overall"), null);
  assert.equal(getScoreForMode(legacyOnly, "financial"), null);
  assert.deepEqual(selectLandingHeroEntries([legacyOnly]), []);
});

test("the prototype openingDesirability score can never surface as Collector Appeal", () => {
  const appeal = selectCollectorAppealBreakdown(CANONICAL);
  assert.notEqual(appeal.publicScore, TARGET.openingDesirability.collectorAppealScore);

  // And the page no longer renders that field under any Collector Appeal label.
  const pageSource = readSource("RipStatisticsPageClient.jsx");
  const code = pageSource
    .split("\n")
    .filter((line) => {
      const trimmed = line.trimStart();
      return !trimmed.startsWith("//") && !trimmed.startsWith("*") && !trimmed.startsWith("/*");
    })
    .join("\n");
  // The prototype score fields must not be read anywhere on the page — not at a
  // render site and not into a normalized object that a future surface could
  // mistake for canonical data.
  // Matched as a property ACCESS (`x.field` / `x?.field`), not as a bare
  // mention: the page also carries a list of field NAMES used purely to decide
  // whether a payload object is empty, and that list reads no value.
  for (const field of [
    "collectorAppealScore",
    "collector_appeal_score",
    "collectorAppealRank",
    "collector_appeal_rank",
    "chaseAppealScore",
    "chase_appeal_score",
    "openingDesirabilityScore",
    "opening_desirability_score",
  ]) {
    const access = new RegExp(`\\??\\.${field}\\b`);
    // Self-check: the pattern must actually match a real property access, so a
    // mis-escaped regex cannot make this assertion pass vacuously.
    assert.equal(access.test(`payload.${field}`), true, `pattern for ${field} is broken`);
    assert.equal(access.test(`payload?.${field}`), true, `pattern for ${field} is broken`);
    assert.equal(access.test(code), false, `the prototype field ${field} must not be read`);
  }

  // "Collector Appeal" may still appear as a heading or a deep-link label — it
  // is a real public metric with a real section. What it may never do is sit
  // beside a value pulled from `openingDesirability`.
  assert.equal(
    /"Collector Appeal",\s*\n?\s*value:/.test(code),
    false,
    "no metric row may be labelled Collector Appeal with a non-canonical value"
  );
});

// =============================================================================
// 4. Rank movement never crosses a scoring model.
// =============================================================================

test("the Explore movement helper is fed canonical previous ranks only", () => {
  const source = readSource("ExploreTableClient.jsx");
  // The frontend reads the published previous-rank fields; the backend decides
  // which model produced them. Assert the two canonical modes are the only ones
  // that can produce a movement at all.
  const helper = source.slice(
    source.indexOf("function getRipMovementForMode"),
    source.indexOf("function toNumber")
  );
  assert.match(helper, /modeId === "overall"/);
  assert.match(helper, /modeId === "financial"/);
  assert.match(helper, /formatRankMovement\(null, currentRank, "unavailable"\)/);
  assert.equal(/pack_rank/.test(helper), false);
});

// =============================================================================
// 5. The RIP Score trend arrow path is gone.
// =============================================================================

test("no RIP Score trend is derived from legacy pack-score history", () => {
  const trends = selectTrendScores({
    summary: { relative_pack_score: 70, pack_score: 55 },
    previousPoint: { relativePackScore: 40, packScore: 30 },
  });
  assert.equal("ripScore" in trends, false, "the RIP Score trend must not be derivable at all");

  const pageSource = readSource("RipStatisticsPageClient.jsx");
  const code = pageSource
    .split("\n")
    .filter((line) => {
      const trimmed = line.trimStart();
      return !trimmed.startsWith("//") && !trimmed.startsWith("*") && !trimmed.startsWith("/*");
    })
    .join("\n");
  assert.equal(/trendByMetricKey\.ripScore/.test(code), false, "no surface may render a RIP Score trend");
  assert.equal(/ripScore:\s*\[/.test(code), false);
});

// =============================================================================
// 6. Outcome metric definitions.
// =============================================================================

test("Expected Value means the mean and Typical Opening means P50", () => {
  const financial = selectFinancialRipV3Breakdown(resolveCanonicalFinancialRip(CANONICAL));
  const byKey = new Map(financial.rows.map((row) => [row.key, row]));

  // Typical Opening's canonical raw value and the summary's median agree.
  const typicalPackValue = CONTRACT.financialRip.components.typical_retention.raw.typicalPackValue;
  assert.equal(typicalPackValue, TARGET.median_value, "P50 must agree across both canonical sources");
  assert.equal(byKey.get("typicalRetention").headline, "$2.40");

  // And the mean is a different number, so a swap cannot pass unnoticed.
  assert.notEqual(TARGET.mean_value, TARGET.median_value);
});

test("Strong Upside and Jackpot Upside are threshold VALUES, never component indexes", () => {
  const financial = selectFinancialRipV3Breakdown(resolveCanonicalFinancialRip(CANONICAL));
  const byKey = new Map(financial.rows.map((row) => [row.key, row]));

  // The public outcome numbers.
  assert.equal(byKey.get("realisticUpside").headline, "$14.25", "Strong Upside is the P95 threshold");
  assert.equal(byKey.get("jackpotUpside").headline, "$61.90", "Jackpot Upside is the top-1% threshold");

  // The normalized component scores exist, differ, and do NOT wear those names.
  assert.equal(byKey.get("realisticUpside").publicScore, 91.2);
  assert.equal(byKey.get("jackpotUpside").publicScore, 88.7);
  const titles = financial.rows.map((row) => row.title);
  assert.equal(titles.includes("Strong Upside"), false, "the bare public name is reserved for the P95 value");
  assert.equal(titles.includes("Jackpot Upside"), false, "the bare public name is reserved for the top-1% value");
});

test("the RTP concepts stay mathematically distinct", () => {
  const financial = selectFinancialRipV3Breakdown(resolveCanonicalFinancialRip(CANONICAL));
  const base = financial.rows.find((row) => row.key === "baseEconomicEfficiency");
  const labels = base.metrics.map((metric) => metric.label);

  assert.ok(labels.includes("Total return to player"));
  assert.ok(labels.includes("Excluding the top 1%"));
  const total = base.metrics.find((m) => m.label === "Total return to player").value;
  const excludingTop = base.metrics.find((m) => m.label === "Excluding the top 1%").value;
  assert.notEqual(total, excludingTop, "total RTP and base RTP are different numbers");

  // Base Economic Efficiency is a normalized SCORE derived from base RTP, and
  // must never be rendered as though it were the RTP percentage itself.
  assert.equal(base.headline, "61.2%", "the card leads with base RTP, the raw ratio");
  assert.notEqual(base.headline, `${base.publicScore}`);
});

// =============================================================================
// 7. Vocabulary.
// =============================================================================

const RETIRED_PUBLIC_VOCABULARY = [
  "Relative RIP Index",
  "Financial Quality",
  "Underlying model score",
  "God Pull Upside",
  "GOD PULL UPSIDE",
  "Rip Score",
  "Rip Rank",
  "relative index",
];

test("no live public surface emits retired vocabulary", () => {
  const surfaces = [
    "RipDecisionPage.jsx",
    "OverviewRipSummary.jsx",
    "InsightsSummaryModule.jsx",
    "FinancialRipV3Breakdown.jsx",
    "CollectorAppealBreakdown.jsx",
    "ExploreTableClient.jsx",
    "ripDrivers.mjs",
    "ripHeroScoreMode.mjs",
    "../landing/RankingTheaterHomepage.jsx",
    "../../lib/landing/landingHeroSpotlight.mjs",
    "../../constants/exploreRankingConfig.mjs",
  ];
  for (const relative of surfaces) {
    const source = readSource(relative);
    // Comments legitimately name what was removed while explaining why.
    const code = source
      .split("\n")
      .filter((line) => {
        const trimmed = line.trimStart();
        return !trimmed.startsWith("//") && !trimmed.startsWith("*") && !trimmed.startsWith("/*");
      })
      .join("\n");
    for (const term of RETIRED_PUBLIC_VOCABULARY) {
      assert.equal(code.includes(term), false, `${relative} still emits "${term}"`);
    }
  }
});

test("the public scale is explained in product language, not as a formula", () => {
  assert.match(PUBLIC_SCORE_SCALE_NOTE, /standardized against currently ranked sets/);
  assert.match(PUBLIC_SCORE_SCALE_NOTE, /100 represents the strongest set/);
  // No arithmetic in a metric tooltip — normalization methodology is the article.
  assert.equal(/min|max|\/\s*\(|percentile/i.test(PUBLIC_SCORE_SCALE_NOTE), false);
});

test("the canonical public names are the ones actually rendered", () => {
  assert.equal(selectRipHeroScoreMode({ canonical: CANONICAL }).label, "Overall RIP");
  const drivers = buildRipDrivers({
    financial: readCanonicalBlock(CANONICAL.financialRip),
    collector: readCanonicalBlock(CANONICAL.collectorAppeal),
    overall: readCanonicalBlock(CANONICAL.overall),
  });
  assert.deepEqual(drivers.drivers.map((d) => d.label).sort(), ["Collector Appeal", "Financial RIP"]);
  // Home's scoreLabel is truthfully "Set RIP" — it is Set RIP V1, not Overall RIP.
  assert.equal(selectLandingHeroEntries([TARGET])[0].scoreLabel, "Set RIP");
  assert.equal(EXPLORE_RANKING_MODES.overall.scoreLabel, "OVERALL RIP");
  assert.equal(EXPLORE_RANKING_MODES.financial.scoreLabel, "FINANCIAL RIP");
});

// =============================================================================
// 8. One scale, one formatting rule.
// =============================================================================

test("every canonical public score formats to one decimal on every surface", () => {
  const financial = selectFinancialRipV3Breakdown(resolveCanonicalFinancialRip(CANONICAL));
  const appeal = selectCollectorAppealBreakdown(CANONICAL);
  assert.equal(financial.publicScoreLabel, "71.9");
  assert.equal(appeal.publicScoreLabel, "95.9");
  assert.equal(formatModeScore(getScoreForMode(TARGET, "overall"), getScoreKind("overall")), "88.4");
  assert.equal(formatModeScore(getScoreForMode(TARGET, "financial"), getScoreKind("financial")), "71.9");
});

test("a cohort leader reads 100.0, not 100", () => {
  const leader = resolveCanonicalRipV7({
    publicRipContractV8: {
      ...CONTRACT,
      overallRip: { ...CONTRACT.overallRip, relativeScore: 100, rank: 1 },
    },
  });
  assert.equal(selectRipHeroScoreMode({ canonical: leader }).publicScore, 100);
  assert.equal(formatModeScore(100, getScoreKind("overall")), "100.0");
});
