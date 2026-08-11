// The canonical V7 contract, end to end across the public surfaces.
//
// These tests are the regression net for the defect this pass fixed: every
// public surface resolved `rip` (Overall RIP **v4** = 90% RIP Core + 10% legacy
// CA7) and published it as "RIP Score". The rules asserted here are:
//
//   1. V7 fields survive frontend normalization.
//   2. A payload carrying BOTH v4 and V7 renders V7.
//   3. Changing the v4 value cannot move the public RIP Score.
//   4. Removing V7 makes the public score UNAVAILABLE - never v4, never zero.
//   5. `publicRipContractV7` wins over the equivalent top-level V7 object.
//   6. V6 Collector Appeal cannot populate the V3 presentation.
//   7. No public legacy toggle or RIP Core switch remains in the source.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  hasCanonicalOverallRipV7,
  readCanonicalBlock,
  resolveCanonicalRipV7,
} from "./canonicalRipV7.mjs";
import { selectRipHeroScoreMode } from "./ripHeroScoreMode.mjs";
import { selectCollectorAppealBreakdown } from "./collectorAppealBreakdownSelector.mjs";
import { resolveCanonicalFinancialRip, selectFinancialRipV3Breakdown } from "./financialRipV3Selector.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const readSource = (relative) => fs.readFileSync(path.resolve(__dirname, relative), "utf8");
// Source files in this repo are CRLF; normalise before any line-anchored match.
const splitLines = (source) => source.split("\n").map((line) => line.replace(/\r$/, ""));

// --- Fixtures ---------------------------------------------------------------
// Shaped after the real backend payload: public_rip_contract_v7.py for the
// packaged contract, explore_rip_statistics_service.py for the top-level
// objects, both carried by get_pokemon_set_insights_critical_snapshot_payload.

const OVERALL_V7_TOP_LEVEL = {
  score: 41.8,
  relativeScore: 73.4,
  rank: 4,
  cohortSize: 21,
  tier: "A",
  version: "overall_rip_v7",
};

const COLLECTOR_APPEAL_V3_BLOCK = {
  score: 62.5,
  absoluteScore: 62.5,
  relativeScore: 70.1,
  rank: 6,
  rankedSetCount: 21,
  tier: "B",
  version: "collector_appeal_v3",
  weightsDisclosed: false,
  components: {
    rosterDesirability: { score: 71.2, rawValue: 0.712 },
    desirableOutcomeFrequency: {
      rawValue: 0.0834,
      impliedOddsOneInN: 12,
      eligibleCardCount: 18,
      eligibleSubjectCount: 7,
      coveredDemandShare: 0.86,
      isFinancialMetric: false,
    },
    dualPathDepth: { rawValue: 0.42, subjectsWithMultiplePaths: 3 },
  },
  subjectScope: {
    modeled: ["Pokémon"],
    notYetModeled: ["Trainer", "Artist"],
    note: "Trainer and artist desirability are not yet modeled. They are omitted from this metric rather than scored as zero.",
  },
};

// Every component carries BOTH layers, with deliberately different values, so
// an assertion can tell which one a surface read.
const FINANCIAL_V3_COMPONENTS = {
  true_win_frequency: { score: 40.1, relativeScore: 74.5, rank: 5, cohortSize: 21, tier: "B", raw: { trueWinProbability: 0.31, packCost: 4.5 } },
  typical_retention: { score: 38.2, relativeScore: 63.0, rank: 7, cohortSize: 21, tier: "C", raw: { typicalPackValue: 2.75 } },
  loss_resilience: { score: 44.9, relativeScore: 79.0, rank: 3, cohortSize: 21, tier: "A", raw: { averageRetentionGivenLoss: 0.54 } },
  realistic_upside: { score: 51.3, relativeScore: 91.2, rank: 2, cohortSize: 21, tier: "A", raw: { p95ThresholdValue: 14.2, realisticTailMeanValue: 21.4 } },
  jackpot_upside: { score: 29.8, relativeScore: 88.7, rank: 11, cohortSize: 21, tier: "D", raw: { p99ThresholdValue: 61.9, jackpotTailMeanValue: 140.5 } },
  base_economic_efficiency: { score: 35.4, relativeScore: 70.1, rank: 8, cohortSize: 21, tier: "C", raw: { totalRtpRatio: 0.82, baseRtpExcludingTop1Pct: 0.61 } },
};

const FINANCIAL_V3_TOP_LEVEL = {
  score: 39.6,
  relativeScore: 68.0,
  rank: 5,
  cohortSize: 21,
  tier: "B",
  status: "ready",
  components: FINANCIAL_V3_COMPONENTS,
  depthAndRobustness: { status: "ready", effectiveChaseCount: 4.2, top1EvShare: 0.31 },
};

const PUBLIC_CONTRACT_V7 = {
  contractVersion: "public_rip_contract_v7",
  overallRip: {
    score: 41.8,
    absoluteScore: 41.8,
    relativeScore: 73.4,
    rank: 4,
    rankedSetCount: 21,
    tier: "A",
    version: "overall_rip_v7",
  },
  financialRip: { ...FINANCIAL_V3_TOP_LEVEL, rankedSetCount: 21 },
  collectorAppeal: COLLECTOR_APPEAL_V3_BLOCK,
};

// Overall RIP v4 — a DIFFERENT model, deliberately given very different numbers
// so any leak is unmistakable in an assertion message.
const LEGACY_V4_RIP = {
  score: 88.8,
  relativeScore: 12.3,
  rank: 19,
  cohortSize: 21,
  tier: "F",
  financialRip: {
    components: {
      profit: { score: 90.1, rank: 1, tier: "S" },
      safety: { score: 91.2, rank: 1, tier: "S" },
      stability: { score: 92.3, rank: 1, tier: "S" },
    },
  },
};

const LEGACY_RIP_CORE = { score: 77.7, relativeScore: 15.5, rank: 18, cohortSize: 21, tier: "F" };

// --- 1. Normalization -------------------------------------------------------
//
// The two insights clients are ESM-syntax `.js` files, which this repo's
// `tsx --test` runner cannot import by name (see
// lib/pokemon/pokemonSetInsightsClient.normalization.test.mjs, which fails the
// same way on an unmodified tree). They are asserted by source inspection, the
// same technique the page-client contract tests use.

const CRITICAL_CLIENT = readSource("../../lib/pokemon/pokemonSetInsightsCriticalClient.js");
const FULL_CLIENT = readSource("../../lib/pokemon/pokemonSetInsightsClient.js");
const PAGE_CLIENT = readSource("./RipStatisticsPageClient.jsx");

test("V7 contract fields survive frontend normalization", () => {
  for (const [name, source] of [["critical", CRITICAL_CLIENT], ["full", FULL_CLIENT]]) {
    assert.ok(
      source.includes("overallRipV7: toPlainObject(payload?.overallRipV7)"),
      `${name} client must pass overallRipV7 through`
    );
    assert.ok(
      source.includes("publicRipContractV7: toPlainObject(payload?.publicRipContractV7)"),
      `${name} client must pass publicRipContractV7 through`
    );
  }
});

test("the page adapters carry V7 into explorePayload", () => {
  // Both the full and the critical adapter, or the hero renders unavailable
  // until the secondary request settles.
  assert.equal(
    (PAGE_CLIENT.match(/publicRipContractV7: (?:normalized|critical)\?\.publicRipContractV7/g) || []).length,
    2
  );
  assert.equal(
    (PAGE_CLIENT.match(/overallRipV7: (?:normalized|critical)\?\.overallRipV7/g) || []).length,
    2
  );
});

test("normalization passes V7 through without deriving anything", () => {
  // `toPlainObject` is the ONLY transformation applied - no defaulting to a
  // legacy object, no computed field, no rename.
  for (const source of [CRITICAL_CLIENT, FULL_CLIENT]) {
    const v7Lines = splitLines(source)
      .filter((line) => /RipV7|RipContractV7/.test(line) && !line.trim().startsWith("//"));
    assert.ok(v7Lines.length >= 2);
    for (const line of v7Lines) {
      assert.match(line, /toPlainObject\(payload\?\.\w+\),$/);
      assert.equal(/\|\||\?\?/.test(line), false, `no fallback allowed on a V7 line: ${line.trim()}`);
    }
  }
});

test("legacy transport fields are retained for audit consumers", () => {
  // Kept in TRANSPORT so internal/debug consumers still resolve. No public
  // surface may read them - asserted by the source checks further down.
  for (const key of ["rip:", "ripCore:", "overallRipV6:", "publicRipContractV6:"]) {
    assert.ok(CRITICAL_CLIENT.includes(key), `${key} must remain in the transport shape`);
  }
});

// --- 2/3/4. The headline score ---------------------------------------------

test("a payload carrying BOTH v4 and V7 renders V7", () => {
  const hero = selectRipHeroScoreMode({
    payload: { rip: LEGACY_V4_RIP, ripCore: LEGACY_RIP_CORE, publicRipContractV7: PUBLIC_CONTRACT_V7 },
  });
  assert.equal(hero.available, true);
  assert.equal(hero.publicScore, 73.4, "public score must be the V7 relative score");
  assert.equal(hero.rank, 4);
  assert.equal(hero.tier, "A");
  assert.equal(hero.cohortSize, 21);
  assert.notEqual(hero.publicScore, LEGACY_V4_RIP.relativeScore);
  assert.notEqual(hero.rank, LEGACY_V4_RIP.rank);
});

test("changing the v4 fixture value does not affect the public RIP Score", () => {
  const base = { publicRipContractV7: PUBLIC_CONTRACT_V7, rip: LEGACY_V4_RIP };
  const mutated = {
    publicRipContractV7: PUBLIC_CONTRACT_V7,
    rip: { ...LEGACY_V4_RIP, score: 3.3, relativeScore: 99.9, rank: 1, tier: "S" },
  };
  const a = selectRipHeroScoreMode({ payload: base });
  const b = selectRipHeroScoreMode({ payload: mutated });
  assert.deepEqual(
    [a.publicScore, a.rank, a.tier, a.cohortSize],
    [b.publicScore, b.rank, b.tier, b.cohortSize],
    "the v4 object must be invisible to the public headline"
  );
});

test("removing V7 makes the public score unavailable rather than showing v4", () => {
  const hero = selectRipHeroScoreMode({
    payload: { rip: LEGACY_V4_RIP, ripCore: LEGACY_RIP_CORE, overallRipV6: { relativeScore: 55, rank: 9 } },
  });
  assert.equal(hero.available, false);
  assert.equal(hero.publicScore, null, "missing canonical data is null, never 0 and never a legacy score");
  assert.equal(hero.rank, null);
  assert.equal(hero.tier, null);
  assert.equal(hero.sourceShape, null);
  assert.equal(hasCanonicalOverallRipV7({ rip: LEGACY_V4_RIP }), false);
});

test("an absolute-only V7 block renders unavailable rather than promoting the model score", () => {
  const hero = selectRipHeroScoreMode({ payload: { overallRipV7: { score: 41.8, rank: 4, tier: "A" } } });
  assert.equal(hero.available, false);
  assert.equal(hero.publicScore, null);
  assert.equal(hero.modelScore, 41.8, "the model score stays available for audit");
});

// --- 5. Shape precedence ----------------------------------------------------

test("publicRipContractV7 takes precedence over equivalent top-level V7 data", () => {
  const resolved = resolveCanonicalRipV7({
    publicRipContractV7: PUBLIC_CONTRACT_V7,
    overallRipV7: { ...OVERALL_V7_TOP_LEVEL, relativeScore: 11.1, rank: 20 },
  });
  assert.equal(resolved.shape, "publicRipContractV7");
  assert.equal(readCanonicalBlock(resolved.overall).publicScore, 73.4);
  assert.equal(readCanonicalBlock(resolved.overall).rank, 4);
});

test("the top-level V7 object is accepted as the same-model shape fallback", () => {
  const hero = selectRipHeroScoreMode({ payload: { overallRipV7: OVERALL_V7_TOP_LEVEL, rip: LEGACY_V4_RIP } });
  assert.equal(hero.sourceShape, "topLevelV7");
  assert.equal(hero.publicScore, 73.4);
  // `cohortSize` at top level, `rankedSetCount` on the contract — one backend
  // denominator read under either name, never recomputed.
  assert.equal(hero.cohortSize, 21);
});

test("the resolver never reads V6/V5/v4/V2 keys", () => {
  const resolved = resolveCanonicalRipV7({
    rip: LEGACY_V4_RIP,
    ripCore: LEGACY_RIP_CORE,
    overallRipV6: OVERALL_V7_TOP_LEVEL,
    publicRipContractV6: PUBLIC_CONTRACT_V7,
    overallRipV5: OVERALL_V7_TOP_LEVEL,
  });
  assert.equal(resolved.shape, null);
  assert.deepEqual(resolved.overall, {});
  assert.deepEqual(resolved.collectorAppeal, {});
  assert.deepEqual(resolved.financialRip, {});
});

// --- 6. Collector Appeal V3 -------------------------------------------------

test("Collector Appeal reads the V7 contract and shows exactly three factors", () => {
  const appeal = selectCollectorAppealBreakdown({ publicRipContractV7: PUBLIC_CONTRACT_V7 });
  assert.equal(appeal.available, true);
  assert.equal(appeal.publicScore, 70.1, "the public value is the relative score");
  assert.equal(appeal.modelScore, 62.5, "the model score stays available for audit");
  assert.equal("score" in appeal, false, "no ambiguous generic `score` key");
  assert.equal(appeal.rank, 6);
  assert.equal(appeal.rankedSetCount, 21);
  assert.deepEqual(
    appeal.rows.map((row) => row.key),
    ["rosterDesirability", "desirableOutcomeFrequency", "dualPathDepth"]
  );
  assert.deepEqual(
    appeal.rows.map((row) => row.title),
    ["Roster Desirability", "Desirable Outcome Frequency", "Dual-Path Depth"]
  );
});

test("V6 Collector Appeal cannot populate the V3 presentation", () => {
  const appeal = selectCollectorAppealBreakdown({
    publicRipContractV6: PUBLIC_CONTRACT_V7,
    overallRipV6: { components: { collectorAppeal: { score: 62.5 } } },
    openingExperience: { collectorAppeal: { score: 62.5, rank: 6, tier: "B" } },
  });
  assert.equal(appeal.available, false);
  assert.equal(appeal.publicScore, null);
  assert.equal(appeal.sourceShape, null);
  // Each factor is independently unavailable and rendered as an em dash.
  assert.deepEqual(appeal.rows.map((row) => row.available), [false, false, false]);
  assert.deepEqual(appeal.rows.map((row) => row.value), ["—", "—", "—"]);
});

test("Roster Desirability never substitutes for a missing Collector Appeal", () => {
  const appeal = selectCollectorAppealBreakdown({
    publicRipContractV7: {
      ...PUBLIC_CONTRACT_V7,
      collectorAppeal: {
        score: null,
        statusReason: "desirable_outcome_frequency_unavailable",
        components: { rosterDesirability: { score: 71.2 } },
      },
    },
  });
  assert.equal(appeal.available, false);
  assert.equal(appeal.publicScore, null);
  // The one factor that IS present still renders on its own terms.
  assert.equal(appeal.rows[0].available, true);
  assert.equal(appeal.rows[0].value, "71.2");
  assert.equal(appeal.rows[1].available, false);
  assert.equal(appeal.statusReason, "desirable_outcome_frequency_unavailable");
});

test("the appeal breakdown exposes no weights and no per-factor contributions", () => {
  const appeal = selectCollectorAppealBreakdown({ publicRipContractV7: PUBLIC_CONTRACT_V7 });
  const serialized = JSON.stringify(appeal);
  for (const forbidden of ["weight", "contribution", "dContribution", "formula"]) {
    assert.equal(
      new RegExp(forbidden, "i").test(serialized),
      false,
      `"${forbidden}" must not appear anywhere in the Collector Appeal view model`
    );
  }
});

test("the non-financial disclaimer and the subject-scope limitation are present", () => {
  const appeal = selectCollectorAppealBreakdown({ publicRipContractV7: PUBLIC_CONTRACT_V7 });
  const frequency = appeal.rows.find((row) => row.key === "desirableOutcomeFrequency");
  assert.equal(frequency.isFinancialMetric, false);
  assert.match(frequency.disclaimer, /worth less than the pack price/i);
  assert.match(appeal.subjectScope.note, /Trainer and artist/i);
  assert.deepEqual(appeal.subjectScope.notYetModeled, ["Trainer", "Artist"]);
});

test("Desirable Outcome Frequency is never labelled as a financial result", () => {
  const appeal = selectCollectorAppealBreakdown({ publicRipContractV7: PUBLIC_CONTRACT_V7 });
  const text = JSON.stringify(appeal);
  for (const forbidden of [/win rate/i, /profit rate/i, /chance to beat cost/i, /break[- ]even/i, /\bhit rate\b/i]) {
    assert.equal(forbidden.test(text), false, `forbidden vocabulary: ${forbidden}`);
  }
});

// --- Financial RIP V3 -------------------------------------------------------

test("Financial RIP prefers the packaged contract and shows exactly six components", () => {
  const canonical = resolveCanonicalFinancialRip({
    publicRipContractV7: PUBLIC_CONTRACT_V7,
    financialRipV3: { ...FINANCIAL_V3_TOP_LEVEL, score: 1.1 },
  });
  const v3 = selectFinancialRipV3Breakdown(canonical, {});
  assert.equal(v3.publicScore, 68.0, "the contract block wins over the top-level object");
  assert.equal(v3.modelScore, 39.6, "the model score stays available for audit");
  assert.equal("score" in v3, false, "no ambiguous generic `score` key");
  assert.equal(v3.rows.length, 6);
  assert.deepEqual(
    v3.rows.map((row) => row.title),
    [
      "Win Frequency",
      "Typical Retention",
      "Loss Resilience",
      // NOT the bare public outcome-metric names: those mean the P95 and P99
      // threshold VALUES, not a 0-100 component index.
      "Strong Upside Quality",
      "Jackpot Upside Quality",
      "Base Economic Efficiency",
    ]
  );
  for (const row of v3.rows) {
    assert.equal("weight" in row, false, "no component may carry a visible weight");
    assert.equal("contribution" in row, false, "no component may carry a contribution");
  }
});

test("Financial RIP never falls back to ripCore (Financial RIP V2)", () => {
  const canonical = resolveCanonicalFinancialRip({ ripCore: LEGACY_RIP_CORE, rip: LEGACY_V4_RIP });
  assert.deepEqual(canonical, {});
  const v3 = selectFinancialRipV3Breakdown(canonical, {});
  assert.equal(v3.diagnostics.status, "unavailable");
  assert.equal(v3.publicScore, null);
  assert.deepEqual(v3.rows.map((row) => row.publicScore), [null, null, null, null, null, null]);
  assert.deepEqual(v3.rows.map((row) => row.publicScoreLabel), ["—", "—", "—", "—", "—", "—"]);
  assert.deepEqual(v3.rows.map((row) => row.available), [false, false, false, false, false, false]);
});

// The Explore leaderboard modes are asserted beside their config, in
// constants/exploreRankingConfig.test.mjs.

// --- 7. Source-text guarantees ---------------------------------------------

// Comments in these files legitimately NAME the removed strings while
// explaining why they were removed, so every source assertion below runs
// against the code with comment lines stripped.
function codeOnly(source) {
  return splitLines(source)
    .filter((line) => {
      const trimmed = line.trim();
      return !trimmed.startsWith("//") && !trimmed.startsWith("*") && !trimmed.startsWith("/*");
    })
    .join("\n");
}

test("no public legacy toggle or RIP Core switch remains", () => {
  const client = codeOnly(readSource("./RipStatisticsPageClient.jsx"));
  const financial = codeOnly(readSource("./FinancialRipV3Breakdown.jsx"));
  const appeal = codeOnly(readSource("./CollectorAppealBreakdown.jsx"));
  const hero = codeOnly(readSource("./ripHeroScoreMode.mjs"));

  assert.equal(client.includes("function RipScoreModeToggle"), false);
  assert.equal(client.includes("<RipScoreModeToggle"), false);
  assert.equal(hero.includes("RIP_CORE_MODE"), false);
  assert.equal(financial.includes("function ModelToggle"), false);
  assert.equal(financial.includes("function LegacyV2Cards"), false);
  assert.equal(financial.includes("FINANCIAL_RIP_MODEL_MODES"), false);
  // The component renders exactly one model heading.
  assert.equal(financial.includes('"Legacy Financial RIP V2"'), false);
  assert.equal(appeal.includes("How Overall RIP is built"), false);
  assert.equal(appeal.includes("formatWeightPercent"), false);
  assert.equal(appeal.includes("Contributes "), false);
});

test("the public breakdown renders no weights, contributions or opening outlook", () => {
  const client = readSource("./RipStatisticsPageClient.jsx");
  const start = client.indexOf("function RipScoreBreakdownModule(");
  const section = client.slice(start, client.indexOf("function StatTile(", start));
  assert.ok(start > -1, "the module must still exist");
  assert.equal(/data-insights-opening-outlook/.test(section), false);
  assert.equal(/Opening Outlook/.test(section), false);
  assert.equal(/of RIP Core/.test(section), false);
  assert.equal(/Contribution to/.test(section), false);
  assert.equal(/coreWeightLabel|coreWeightsCaption/.test(section), false);
  // The two explanatory lenses, and nothing between them. They are NOT halves:
  // no copy here may state or imply an equal split.
  assert.ok(section.includes("<FinancialRipV3Breakdown"));
  assert.ok(section.includes("<CollectorAppealBreakdown"));
  assert.equal(/two canonical halves|equal halves|one of the two halves/.test(section), false);
  // Both lenses are fed the SAME resolved bundle, so neither can resolve its
  // own source and disagree with the score rendered above them.
  assert.ok(section.includes("<FinancialRipV3Breakdown canonical={canonical}"));
  assert.ok(section.includes("<CollectorAppealBreakdown canonical={canonical}"));
});

test("Decision Signals no longer render on Overview", () => {
  const client = readSource("./RipStatisticsPageClient.jsx");
  assert.equal(client.includes("<DecisionSignalsCard"), false);
  assert.equal(client.includes("function DecisionSignalsCard("), false);
  assert.equal(client.includes("function DecisionSignalsCompactList("), false);
  assert.equal(client.includes("selectDecisionSignals"), false);
  // ...and its nav entry went with it, so no tab links to a missing anchor.
  assert.equal(/label: "Decision Signals"/.test(client), false);
});

test("no hero surface renders the obsolete interpretation badge or summary", () => {
  const client = readSource("./RipStatisticsPageClient.jsx");
  assert.equal(client.includes("data-rip-summary-pill"), false);
  assert.equal(client.includes("data-set-context-rip-verdict"), false);
  assert.equal(client.includes("function RecommendationBadge"), false);
  assert.equal(/const recommendationBadge =/.test(client), false);
  assert.equal(/const recommendationSummary =/.test(client), false);
});

test("\"View analysis\" replaces \"View verdict\" and keeps its navigation target", () => {
  const client = readSource("./RipStatisticsPageClient.jsx");
  assert.equal(client.includes("View verdict"), false);
  assert.ok(client.includes("View analysis"));
  const cta = client.slice(client.indexOf("data-set-context-rip-helper"), client.indexOf("View analysis") + 20);
  assert.ok(
    cta.includes('handleSetDetailNavSelect({ tab: "insights", section: "rip-score", targetId: "set-detail-rip-score" })'),
    "the CTA must keep its existing destination"
  );
});

test("the hero selector reads no legacy field in any code path", () => {
  const hero = codeOnly(readSource("./ripHeroScoreMode.mjs"));
  const resolver = codeOnly(readSource("./canonicalRipV7.mjs"));
  for (const [name, source] of [["ripHeroScoreMode", hero], ["canonicalRipV7", resolver]]) {
    for (const legacy of ['"rip"', '"ripCore"', "overallRipV6", "overallRipV5", "pack_score", "relative_pack_score", "pack_rank"]) {
      assert.equal(source.includes(legacy), false, `${name} must not read ${legacy}`);
    }
  }
});

// --- One resolved bundle, shared by every surface ---------------------------
//
// The defect these cover: the set page used to resolve each canonical object
// with its own `explorePayload?.x || selectedTarget?.x || summary?.x` chain.
// A normalized-but-empty `{}` is TRUTHY, so an empty object in the first source
// won its chain and blocked populated canonical data in a later one. Because
// the three chains were independent, they could also settle on three different
// sources and split the hero from the sections that explain it.

// The shape the page actually passes, with the first source normalized to empty
// objects — exactly what a set-page payload looks like before its snapshot
// lands, and what the old truthiness chains choked on.
const EMPTY_FIRST_SOURCE = {
  publicRipContractV7: {},
  overallRipV7: {},
  financialRipV3: {},
};

const POPULATED_CONTRACT = {
  publicRipContractV7: {
    overallRip: { relativeScore: 71.5, rank: 12, tier: "A", rankedSetCount: 240 },
    financialRip: {
      status: "ready",
      score: 68.25,
      absoluteScore: 68.25,
      relativeScore: 71.9,
      rank: 15,
      tier: "A",
      rankedSetCount: 240,
      components: {
        true_win_frequency: { score: 61.1, relativeScore: 66.4, rank: 30, tier: "B", raw: { trueWinProbability: 0.21 } },
      },
    },
    collectorAppeal: {
      score: 82.4,
      absoluteScore: 82.4,
      relativeScore: 90.2,
      rank: 5,
      tier: "S",
      rankedSetCount: 240,
      components: {
        rosterDesirability: { score: 88.1 },
        desirableOutcomeFrequency: { rawValue: 0.34, impliedOddsOneInN: 2.9 },
        dualPathDepth: { rawValue: 0.62, subjectsWithMultiplePaths: 9 },
      },
    },
  },
};

test("an empty V7 object in the first source does not block a valid later contract", () => {
  const resolved = resolveCanonicalRipV7(EMPTY_FIRST_SOURCE, POPULATED_CONTRACT, {});

  assert.equal(resolved.shape, "publicRipContractV7");
  // Not blocked, and not partially blocked: all three blocks come through.
  assert.equal(readCanonicalBlock(resolved.overall).publicScore, 71.5);
  assert.equal(readCanonicalBlock(resolved.financialRip).publicScore, 71.9);
  assert.equal(resolved.financialRip.absoluteScore, 68.25);
  assert.equal(resolved.collectorAppeal.absoluteScore, 82.4);
});

test("the hero, Financial RIP and Collector Appeal all read the one resolved bundle", () => {
  // Resolved ONCE, the way the page does it, then handed to all three surfaces.
  const canonical = resolveCanonicalRipV7(EMPTY_FIRST_SOURCE, POPULATED_CONTRACT, {});

  const hero = selectRipHeroScoreMode({ canonical });
  const financial = selectFinancialRipV3Breakdown(resolveCanonicalFinancialRip(canonical));
  const appeal = selectCollectorAppealBreakdown(canonical);

  // Every surface renders the selected target's canonical data. Before the
  // single-bundle change each of these resolved independently and every one of
  // them landed on the empty first source instead.
  assert.equal(hero.available, true);
  assert.equal(hero.publicScore, 71.5);
  assert.equal(hero.tier, "A");
  assert.equal(hero.rank, 12);

  assert.equal(financial.publicScore, 71.9);
  assert.equal(financial.diagnostics.status, "ready");
  assert.equal(financial.rows.length, 6);

  assert.equal(appeal.available, true);
  assert.equal(appeal.publicScore, 90.2);
  assert.equal(appeal.rows.length, 3);

  // ...and all three agree on WHICH source answered.
  assert.equal(hero.sourceShape, "publicRipContractV7");
  assert.equal(appeal.sourceShape, "publicRipContractV7");
});

test("a populated contract in the first source wins over conflicting later top-level data", () => {
  const conflictingLater = {
    overallRipV7: { relativeScore: 11.1, rank: 999, tier: "F", cohortSize: 240 },
    financialRipV3: { status: "ready", score: 9.9, components: { true_win_frequency: { score: 1 } } },
  };

  const canonical = resolveCanonicalRipV7(POPULATED_CONTRACT, conflictingLater, {});
  const hero = selectRipHeroScoreMode({ canonical });

  // Contract-over-top-level precedence, unchanged by the single-bundle work.
  assert.equal(canonical.shape, "publicRipContractV7");
  assert.equal(hero.publicScore, 71.5);
  assert.equal(hero.tier, "A");
  assert.equal(selectFinancialRipV3Breakdown(resolveCanonicalFinancialRip(canonical)).publicScore, 71.9);
});

test("resolving an already-resolved bundle returns it unchanged", () => {
  // The page resolves once and passes the bundle down; selectors still call the
  // resolver. If a bundle were treated as a raw source it would be searched for
  // a `publicRipContractV7` key it does not have, resolve to unavailable, and
  // blank every downstream surface.
  const canonical = resolveCanonicalRipV7(POPULATED_CONTRACT);

  assert.equal(resolveCanonicalRipV7(canonical), canonical);
  // ...and it wins over later raw sources, because it IS the resolution.
  assert.equal(resolveCanonicalRipV7(canonical, { publicRipContractV7: { overallRip: { relativeScore: 3 } } }), canonical);
  assert.equal(selectRipHeroScoreMode({ canonical }).publicScore, 71.5);
});

test("a bundle with no canonical data renders unavailable, never zero", () => {
  const canonical = resolveCanonicalRipV7(EMPTY_FIRST_SOURCE, {}, {});

  assert.equal(canonical.shape, null);
  const hero = selectRipHeroScoreMode({ canonical });
  assert.equal(hero.available, false);
  assert.equal(hero.publicScore, null);
  assert.equal(selectCollectorAppealBreakdown(canonical).available, false);
  assert.equal(selectFinancialRipV3Breakdown(resolveCanonicalFinancialRip(canonical)).diagnostics.status, "unavailable");
});
