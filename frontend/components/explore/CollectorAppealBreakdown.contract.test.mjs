// Collector Appeal (D / F / P) and the 80/20 Overall RIP composition —
// frontend contract tests.
//
// The claims under test:
//   * the Overall breakdown shows 80% and 20%,
//   * Collector Appeal shows D, F and P,
//   * Desirable Outcome Frequency is never labelled a financial win,
//   * Financial RIP still shows exactly six components and gains no seventh,
//   * a missing F renders as an em dash, never as 0%,
//   * Legacy V2 remains explicitly labelled,
//   * mobile and desktop layout contracts are preserved.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  DESIRABLE_OUTCOME_DISCLAIMER,
  FINANCIAL_VS_COLLECTOR_NOTE,
  formatApproximateOdds,
  formatPercentFromUnit,
  formatWeightPercent,
  selectCollectorAppealBreakdown,
  selectOverallRipComposition,
} from "./collectorAppealBreakdownSelector.mjs";
import { selectFinancialRipV3Breakdown } from "./financialRipV3Selector.mjs";
import { selectRipScoreBreakdown } from "./ripScoreBreakdownSelector.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
// Mixed CRLF/LF lives in this directory; normalize before any source assertion.
const readSource = (name) =>
  fs.readFileSync(path.join(here, name), "utf8").replace(/\r\n/g, "\n");

const componentSource = readSource("CollectorAppealBreakdown.jsx");
const selectorSource = readSource("collectorAppealBreakdownSelector.mjs");
const pageSource = readSource("RipStatisticsPageClient.jsx");

// --- Fixture: the shaped publicRipContractV6 block --------------------------

const V6_FIXTURE = {
  contractVersion: "public_rip_contract_v6",
  overallRip: {
    score: 57.75,
    rank: 4,
    rankedSetCount: 21,
    tier: "A",
    version: "overall_rip_v6_80_financial_v3_20_collector_appeal_v2",
    components: {
      financialRipV3: { score: 55.7665, weight: 0.8, contribution: 44.6132 },
      collectorAppeal: { score: 65.6858, weight: 0.2, contribution: 13.1372 },
    },
  },
  collectorAppeal: {
    score: 65.6858,
    rank: 3,
    rankedSetCount: 21,
    tier: "A",
    version: "collector_appeal_v2_desirable_frequency_dual_path",
    structuralOpeningAppeal: 0.193991,
    headroomBonus: 0.036858,
    components: {
      rosterDesirability: { score: 62.0, rawValue: 0.62, version: "universal_set_desirability_v3" },
      desirableOutcomeFrequency: {
        rawValue: 0.031,
        displayPercent: 3.1,
        impliedOddsOneInN: 32.26,
        eligibleCardCount: 24,
        eligibleSubjectCount: 8,
        coveredDemandShare: 0.93,
        slotGroupCount: 3,
        status: "available",
        isFinancialMetric: false,
      },
      dualPathDepth: { rawValue: 0.4385, displayPercent: 43.8, subjectsWithMultiplePaths: 5 },
    },
  },
};

// --- Overall RIP composition ------------------------------------------------

test("the Overall RIP breakdown shows 80% and 20%", () => {
  const composition = selectOverallRipComposition({ publicRipContractV6: V6_FIXTURE });
  assert.equal(composition.available, true);
  assert.deepEqual(
    composition.rows.map((row) => row.title),
    ["Financial RIP", "Collector Appeal"]
  );
  assert.equal(composition.rows[0].weight, 0.8);
  assert.equal(composition.rows[1].weight, 0.2);
  assert.equal(formatWeightPercent(composition.rows[0].weight), "80%");
  assert.equal(formatWeightPercent(composition.rows[1].weight), "20%");
  // Rendered, not merely selected.
  assert.match(componentSource, /Overall RIP = 80% Financial RIP \+ 20% Collector Appeal/);
});

test("both source scores and both contributions are shown so the split is checkable", () => {
  const composition = selectOverallRipComposition({ publicRipContractV6: V6_FIXTURE });
  const [financial, appeal] = composition.rows;
  assert.equal(financial.score, 55.7665);
  assert.equal(appeal.score, 65.6858);
  assert.ok(
    Math.abs(financial.contribution + appeal.contribution - composition.score) < 0.01,
    "the two contributions must reconstruct the Overall RIP score"
  );
});

test("the page no longer states the retired 90/10 split", () => {
  assert.doesNotMatch(pageSource, /90% RIP Core \+ 10% Collector Appeal/);
  assert.doesNotMatch(pageSource, /RIP Score = 90%/);
  assert.doesNotMatch(pageSource, /RIP Core supplies the other 90%/);
  assert.match(pageSource, /80% Financial RIP \+ 20% Collector Appeal/);
});

// --- Collector Appeal D / F / P ---------------------------------------------

test("Collector Appeal shows Roster Desirability, Desirable Outcome Frequency and Dual-Path Depth", () => {
  const appeal = selectCollectorAppealBreakdown({ publicRipContractV6: V6_FIXTURE });
  assert.equal(appeal.available, true);
  assert.deepEqual(
    appeal.rows.map((row) => row.key),
    ["rosterDesirability", "desirableOutcomeFrequency", "dualPathDepth"]
  );
  assert.deepEqual(
    appeal.rows.map((row) => row.title),
    ["Roster Desirability", "Desirable Outcome Frequency", "Dual-Path Depth"]
  );
});

test("the frequency card shows probability, approximate odds, counts and coverage", () => {
  const appeal = selectCollectorAppealBreakdown({ publicRipContractV6: V6_FIXTURE });
  const frequency = appeal.rows.find((row) => row.key === "desirableOutcomeFrequency");
  assert.equal(frequency.value, "3.1%");
  const labels = frequency.metrics.map((metric) => metric.label);
  assert.deepEqual(labels, [
    "Modeled probability",
    "Approximate odds",
    "Eligible desirable cards",
    "Eligible desirable subjects",
    "Coverage",
  ]);
  const byLabel = new Map(frequency.metrics.map((metric) => [metric.label, metric.value]));
  assert.equal(byLabel.get("Approximate odds"), "approximately 1 in 32 packs");
  assert.equal(byLabel.get("Eligible desirable cards"), "24");
  assert.equal(byLabel.get("Eligible desirable subjects"), "8");
  assert.equal(byLabel.get("Coverage"), "93% of desirable demand modeled");
});

test("modeled odds are worded as approximate, never as a guarantee", () => {
  assert.equal(formatApproximateOdds(12.4), "approximately 1 in 12 packs");
  // Checked against RENDERED STRINGS, not raw source: the selector's own
  // comments legitimately explain why a guarantee must never be implied, and a
  // source-wide search cannot tell that rule from a violation of it.
  const appeal = selectCollectorAppealBreakdown({ publicRipContractV6: V6_FIXTURE });
  const rendered = appeal.rows
    .flatMap((row) => [row.title, row.interpretation, row.disclaimer, row.value, ...row.metrics.map((m) => m.value)])
    .filter(Boolean)
    .join(" ");
  assert.doesNotMatch(rendered, /guarantee/i);
  assert.doesNotMatch(rendered, /\bwill (?:get|pull|contain)\b/i);
  assert.match(rendered, /approximately 1 in/);
});

// --- The vocabulary rule ----------------------------------------------------

test("Desirable Outcome Frequency is never labelled a financial win", () => {
  const appeal = selectCollectorAppealBreakdown({ publicRipContractV6: V6_FIXTURE });
  const frequency = appeal.rows.find((row) => row.key === "desirableOutcomeFrequency");

  const surfaces = [
    frequency.title,
    frequency.interpretation,
    frequency.disclaimer,
    ...frequency.metrics.map((metric) => metric.label),
  ].join(" ");

  for (const forbidden of [
    /\bwin\b/i,
    /\bprofit/i,
    /break[- ]even/i,
    /cost recovery/i,
    /beat cost/i,
    /\bhit rate\b/i,
  ]) {
    assert.doesNotMatch(surfaces, forbidden, `frequency copy must not match ${forbidden}`);
  }
  assert.equal(frequency.isFinancialMetric, false);
});

test("the frequency card carries the loss disclaimer next to the number", () => {
  const appeal = selectCollectorAppealBreakdown({ publicRipContractV6: V6_FIXTURE });
  const frequency = appeal.rows.find((row) => row.key === "desirableOutcomeFrequency");
  assert.equal(frequency.disclaimer, DESIRABLE_OUTCOME_DISCLAIMER);
  assert.match(frequency.disclaimer, /can still be worth less than the pack price/);
  // Rendered, not merely selected.
  assert.match(componentSource, /data-desirable-outcome-disclaimer/);
});

test("the financial vs collector distinction is stated on the surface", () => {
  assert.match(
    FINANCIAL_VS_COLLECTOR_NOTE,
    /Financial RIP measures monetary pack outcomes\. Collector Appeal measures/
  );
  assert.match(componentSource, /data-financial-collector-distinction/);
  assert.match(componentSource, /FINANCIAL_VS_COLLECTOR_NOTE/);
});

test("Trainer and Artist are omitted, never rendered as zero or 'not desirable'", () => {
  const appeal = selectCollectorAppealBreakdown({ publicRipContractV6: V6_FIXTURE });
  assert.ok(!appeal.rows.some((row) => /trainer|artist/i.test(row.title)));
  assert.deepEqual(appeal.subjectScope.notYetModeled, ["Trainer", "Artist"]);
  assert.match(appeal.subjectScope.note, /not yet modeled/i);
  assert.doesNotMatch(appeal.subjectScope.note, /not desirable/i);
  assert.match(componentSource, /data-collector-appeal-subject-scope/);
});

// --- Financial RIP is untouched ---------------------------------------------

test("Financial RIP still shows exactly six components and gains no seventh", () => {
  const financial = selectFinancialRipV3Breakdown({
    status: "ready",
    score: 55.7,
    components: Object.fromEntries(
      [
        "true_win_frequency",
        "typical_retention",
        "loss_resilience",
        "realistic_upside",
        "jackpot_upside",
        "base_economic_efficiency",
      ].map((key) => [key, { score: 50, rank: 1, cohortSize: 21, raw: {} }])
    ),
  });
  assert.equal(financial.rows.length, 6);
  assert.ok(
    !financial.rows.some((row) => /desirab|frequency|collector/i.test(row.title)),
    "Desirable Outcome Frequency must never appear as a financial component"
  );
});

test("the Collector Appeal surface does not inject a component into the financial breakdown", () => {
  // The two surfaces are separate components reading separate selectors.
  assert.doesNotMatch(componentSource, /FinancialRipV3Breakdown/);
  assert.doesNotMatch(selectorSource, /trueWinFrequency|realisticUpside|jackpotUpside/);
});

test("Legacy V2 remains explicitly labelled", () => {
  const financialSource = readSource("FinancialRipV3Breakdown.jsx");
  assert.match(financialSource, /"Legacy Financial RIP V2"/);
  assert.match(financialSource, /label:\s*"Legacy V2"/);
  assert.match(financialSource, /label:\s*"Current V3"/);
  // And the legacy selector still returns its three pillars.
  const legacy = selectRipScoreBreakdown(
    {
      financialRip: {
        components: {
          profit: { score: 61.1, rank: 2, cohortSize: 21 },
          safety: { score: 22.6, rank: 14, cohortSize: 21 },
          stability: { score: 26.5, rank: 11, cohortSize: 21 },
        },
      },
    },
    {}
  );
  assert.deepEqual(legacy.rows.map((row) => row.title), ["Profit", "Safety", "Stability"]);
});

// --- Missing data -----------------------------------------------------------

test("a missing F renders as an em dash, never as 0%", () => {
  const missing = {
    ...V6_FIXTURE,
    collectorAppeal: {
      ...V6_FIXTURE.collectorAppeal,
      components: {
        ...V6_FIXTURE.collectorAppeal.components,
        desirableOutcomeFrequency: {
          rawValue: null,
          status: "unavailable",
          statusReason: "desirable_outcome_frequency_unavailable_insufficient_coverage",
        },
      },
    },
  };
  const appeal = selectCollectorAppealBreakdown({ publicRipContractV6: missing });
  const frequency = appeal.rows.find((row) => row.key === "desirableOutcomeFrequency");
  assert.equal(frequency.value, "—");
  assert.equal(frequency.available, false);
  assert.notEqual(frequency.value, "0%");
  assert.notEqual(frequency.value, "0.0%");
  for (const metric of frequency.metrics) {
    assert.notEqual(metric.value, "0%", `${metric.label} must not render as 0%`);
  }
  assert.equal(frequency.statusReason, "desirable_outcome_frequency_unavailable_insufficient_coverage");
});

test("a genuine zero still renders as zero", () => {
  assert.equal(formatPercentFromUnit(0), "0.0%");
  assert.equal(formatPercentFromUnit(null), "—");
  assert.equal(formatWeightPercent(0.2), "20%");
});

test("an unavailable Overall RIP does not render a fabricated score", () => {
  const composition = selectOverallRipComposition({
    publicRipContractV6: {
      overallRip: {
        score: null,
        statusReason: "Overall RIP V6 needs a valid Financial RIP V3 and a valid Collector Appeal.",
        missingInputs: ["collector_appeal"],
        components: {},
      },
    },
  });
  assert.equal(composition.available, false);
  assert.equal(composition.score, null);
  assert.equal(composition.scoreLabel, "—");
  assert.deepEqual(composition.missingInputs, ["collector_appeal"]);
});

test("the selector never falls back to a legacy model", () => {
  const code = selectorSource
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !line.trimStart().startsWith("//"))
    .join("\n");
  assert.doesNotMatch(code, /overallRipV5/);
  assert.doesNotMatch(code, /overallRipV4/);
  assert.doesNotMatch(code, /legacyCollectorAppealCA7/);
  assert.doesNotMatch(code, /ripCore/);
  const appeal = selectCollectorAppealBreakdown({ publicRipContractV6: V6_FIXTURE });
  assert.equal(appeal.fallbackUsed, false);
});

// --- Wiring and layout ------------------------------------------------------

test("the breakdown is mounted and fed the canonical v6 objects", () => {
  assert.match(pageSource, /import CollectorAppealBreakdown from "\.\/CollectorAppealBreakdown\.jsx";/);
  const start = pageSource.indexOf("function RipScoreBreakdownModule");
  const end = pageSource.indexOf("function StatTile", start);
  assert.ok(start >= 0 && end > start);
  const module = pageSource.slice(start, end);
  assert.match(module, /<CollectorAppealBreakdown/);
  assert.match(module, /publicRipContractV6=\{publicRipContractV6\}/);
  assert.match(module, /overallRipV6=\{overallRipV6\}/);
});

test("overallRipV6 survives every allow-listing layer between API and page", async () => {
  const { normalizePokemonSetInsightsCriticalPayload } = await import(
    "../../lib/pokemon/pokemonSetInsightsCriticalClient.js"
  );
  const normalized = normalizePokemonSetInsightsCriticalPayload({
    set: { id: "s1", name: "Test", slug: "test" },
    overallRipV6: { score: 57.75 },
    publicRipContractV6: V6_FIXTURE,
    meta: { warnings: [] },
  });
  assert.equal(normalized.overallRipV6.score, 57.75);
  assert.equal(normalized.publicRipContractV6.contractVersion, "public_rip_contract_v6");

  const criticalAdapter = pageSource.slice(
    pageSource.indexOf("function adaptPokemonSetInsightsCriticalPayloadToExplorePayload"),
    pageSource.indexOf("function adaptPokemonSetInsightsSecondaryPayloadToExplorePayload")
  );
  assert.match(criticalAdapter, /overallRipV6: critical\?\.overallRipV6/);
  assert.match(criticalAdapter, /publicRipContractV6: critical\?\.publicRipContractV6/);
});

test("the page resolves the v6 objects without defaulting to a legacy model", () => {
  const start = pageSource.indexOf("const canonicalOverallRipV6 = useMemo(");
  assert.ok(start >= 0, "the page must resolve canonicalOverallRipV6");
  const block = pageSource.slice(start, start + 700);
  assert.match(block, /explorePayload\?\.overallRipV6/);
  assert.doesNotMatch(block, /overallRipV5/);
  assert.doesNotMatch(block, /ripCore/);
});

test("mobile and desktop layout contracts are preserved", () => {
  const grids = componentSource.match(/className="[^"]*grid[^"]*"/g) || [];
  assert.ok(grids.length > 0);
  for (const grid of grids) {
    assert.match(grid, /min-w-0|gap-/, `grid must be constrained: ${grid}`);
  }
  // Responsive, not a fixed multi-column row.
  assert.match(componentSource, /desk:grid-cols-2/);
  assert.match(componentSource, /desk:grid-cols-3/);
  // Same mobile-feed treatment as the surrounding sections.
  assert.match(componentSource, /max-desk:rounded-none max-desk:border-0/);
  // Numbers are tabular so columns do not jitter between sets.
  assert.match(componentSource, /tabular-nums/);
  // No new colour tokens: every colour utility must resolve to an existing CSS
  // custom property. Arbitrary SIZE values (text-[11px]) are excluded - those
  // are the page's existing type scale, not colours.
  const colours = (componentSource.match(/(?:text|bg|border)-\[([^\]]+)\]/g) || []).filter(
    (token) => !/\[\d+(?:\.\d+)?(?:px|rem|em|%)\]$/.test(token)
  );
  assert.ok(colours.length > 0, "the component should use themed colour tokens");
  for (const token of colours) {
    assert.match(token, /var\(--/, `unexpected literal colour: ${token}`);
  }
});
