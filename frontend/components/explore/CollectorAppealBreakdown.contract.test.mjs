// Collector Appeal V3 — frontend contract tests.
//
// WHAT CHANGED IN THIS FILE
// -------------------------
// It used to assert an 80/20 Overall RIP composition read from
// `publicRipContractV6`, with per-term weight pills, contribution points, and a
// `Current V3 / Legacy V2` toggle beside it. All of that described Collector
// Appeal **V2** under the current product name. The canonical model is
// Collector Appeal V3, read from `publicRipContractV7`, explained by three
// PARALLEL factors, with no weights and no contributions published at all.
//
// The claims under test now:
//   * the selector reads the V7 contract and V6 cannot feed it,
//   * Collector Appeal shows exactly D, F and P, as parallel factors,
//   * no weight, contribution or composition arithmetic is rendered,
//   * Desirable Outcome Frequency is never labelled a financial win,
//   * Financial RIP still shows exactly six components and gains no seventh,
//   * a missing factor renders as an em dash, never as 0%,
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
  selectCollectorAppealBreakdown,
} from "./collectorAppealBreakdownSelector.mjs";
import { selectFinancialRipV3Breakdown } from "./financialRipV3Selector.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
// Mixed CRLF/LF lives in this directory; normalize before any source assertion.
const readSource = (name) =>
  fs.readFileSync(path.join(here, name), "utf8").replace(/\r\n/g, "\n");

const componentSource = readSource("CollectorAppealBreakdown.jsx");
const selectorSource = readSource("collectorAppealBreakdownSelector.mjs");
const pageSource = readSource("RipStatisticsPageClient.jsx");

const stripComments = (source) =>
  source
    .split("\n")
    .filter((line) => {
      const trimmed = line.trimStart();
      return !trimmed.startsWith("//") && !trimmed.startsWith("*") && !trimmed.startsWith("/*");
    })
    .join("\n");

// --- Fixture: the shaped publicRipContractV7 block --------------------------
// Shaped after backend/desirability/public_rip_contract_v7.py. Note what it
// does NOT carry: no weights, no per-factor contribution, no formula. The
// backend withholds them (`weightsDisclosed: false`) and the frontend must not
// reconstruct them.

const V7_FIXTURE = {
  contractVersion: "public_rip_contract_v7",
  overallRip: {
    score: 57.75,
    absoluteScore: 57.75,
    relativeScore: 73.4,
    rank: 4,
    rankedSetCount: 21,
    tier: "A",
    version: "overall_rip_v7",
  },
  collectorAppeal: {
    score: 65.6858,
    absoluteScore: 65.6858,
    relativeScore: 70.1,
    rank: 3,
    rankedSetCount: 21,
    tier: "A",
    version: "collector_appeal_v3",
    weightsDisclosed: false,
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
    subjectScope: {
      modeled: ["Pokémon"],
      notYetModeled: ["Trainer", "Artist"],
      note: "Trainer and artist desirability are not yet modeled. They are omitted from this metric rather than scored as zero.",
    },
  },
};

// --- The three parallel factors ---------------------------------------------

test("Collector Appeal shows Roster Desirability, Desirable Outcome Frequency and Dual-Path Depth", () => {
  const appeal = selectCollectorAppealBreakdown({ publicRipContractV7: V7_FIXTURE });
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

test("the score, rank, tier and denominator are the backend's own", () => {
  const appeal = selectCollectorAppealBreakdown({ publicRipContractV7: V7_FIXTURE });
  assert.equal(appeal.score, 65.6858);
  assert.equal(appeal.scoreLabel, "65.7");
  assert.equal(appeal.rank, 3);
  assert.equal(appeal.rankedSetCount, 21);
  assert.equal(appeal.tier, "A");
});

test("the three factors are presented in parallel, not as a sequential chain", () => {
  // A grid of three peers. No arrows, no numbered stages, no connector.
  assert.match(componentSource, /desk:grid-cols-3/);
  assert.doesNotMatch(componentSource, /CollectorProfileArrow|data-collector-profile-flow/);
  // ...and the page no longer renders the old flow anywhere either.
  assert.doesNotMatch(pageSource, /function CollectorProfileArrow\(/);
  assert.doesNotMatch(pageSource, /function CollectorProfileStage\(/);
  assert.doesNotMatch(pageSource, /label="RIP Score Contribution"/);
});

test("the frequency card shows probability, approximate odds, counts and coverage", () => {
  const appeal = selectCollectorAppealBreakdown({ publicRipContractV7: V7_FIXTURE });
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
  const appeal = selectCollectorAppealBreakdown({ publicRipContractV7: V7_FIXTURE });
  const rendered = appeal.rows
    .flatMap((row) => [row.title, row.interpretation, row.disclaimer, row.value, ...row.metrics.map((m) => m.value)])
    .filter(Boolean)
    .join(" ");
  assert.doesNotMatch(rendered, /guarantee/i);
  assert.doesNotMatch(rendered, /\bwill (?:get|pull|contain)\b/i);
  assert.match(rendered, /approximately 1 in/);
});

// --- No internal weights, no contributions, no composition arithmetic -------

test("no factor weight or contribution is selected or rendered", () => {
  const appeal = selectCollectorAppealBreakdown({ publicRipContractV7: V7_FIXTURE });
  const serialized = JSON.stringify(appeal);
  for (const forbidden of [/weight/i, /contribut/i, /formula/i]) {
    assert.doesNotMatch(serialized, forbidden, `view model must not carry ${forbidden}`);
  }
  // Against CODE, not comments: the component's header comment legitimately
  // names the removed strings while explaining why they were removed.
  const code = stripComments(componentSource);
  assert.doesNotMatch(code, /formatWeightPercent/);
  assert.doesNotMatch(code, /Contributes /);
  assert.doesNotMatch(code, /data-overall-composition-term/);
  // The selector no longer exports a composition at all.
  assert.doesNotMatch(selectorSource, /export function selectOverallRipComposition/);
  assert.doesNotMatch(selectorSource, /export function formatWeightPercent/);
});

test("no composition percentage or formula is stated in the rendered copy", () => {
  const code = stripComments(componentSource);
  assert.doesNotMatch(code, /How Overall RIP is built/);
  assert.doesNotMatch(code, /80%|20%|90%|10%/);
  assert.doesNotMatch(code, /Overall RIP =/);
});

// --- The vocabulary rule ----------------------------------------------------

test("Desirable Outcome Frequency is never labelled a financial win", () => {
  const appeal = selectCollectorAppealBreakdown({ publicRipContractV7: V7_FIXTURE });
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
  const appeal = selectCollectorAppealBreakdown({ publicRipContractV7: V7_FIXTURE });
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
  const appeal = selectCollectorAppealBreakdown({ publicRipContractV7: V7_FIXTURE });
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

test("no Legacy V2 comparison remains on the public Financial RIP surface", () => {
  const code = stripComments(readSource("FinancialRipV3Breakdown.jsx"));
  assert.doesNotMatch(code, /"Legacy Financial RIP V2"/);
  assert.doesNotMatch(code, /label:\s*"Legacy V2"/);
  assert.doesNotMatch(code, /label:\s*"Current V3"/);
  assert.doesNotMatch(code, /Profit|Safety|Stability/);
});

// --- Missing data -----------------------------------------------------------

test("a missing F renders as an em dash, never as 0%", () => {
  const missing = {
    ...V7_FIXTURE,
    collectorAppeal: {
      ...V7_FIXTURE.collectorAppeal,
      components: {
        ...V7_FIXTURE.collectorAppeal.components,
        desirableOutcomeFrequency: {
          rawValue: null,
          status: "unavailable",
          statusReason: "desirable_outcome_frequency_unavailable_insufficient_coverage",
        },
      },
    },
  };
  const appeal = selectCollectorAppealBreakdown({ publicRipContractV7: missing });
  const frequency = appeal.rows.find((row) => row.key === "desirableOutcomeFrequency");
  assert.equal(frequency.value, "—");
  assert.equal(frequency.available, false);
  assert.notEqual(frequency.value, "0%");
  assert.notEqual(frequency.value, "0.0%");
  for (const metric of frequency.metrics) {
    assert.notEqual(metric.value, "0%", `${metric.label} must not render as 0%`);
  }
  assert.equal(frequency.statusReason, "desirable_outcome_frequency_unavailable_insufficient_coverage");
  // The other two factors are unaffected: availability is per-factor.
  assert.equal(appeal.rows[0].available, true);
  assert.equal(appeal.rows[2].available, true);
});

test("a genuine zero still renders as zero", () => {
  assert.equal(formatPercentFromUnit(0), "0.0%");
  assert.equal(formatPercentFromUnit(null), "—");
});

test("an unavailable Collector Appeal does not render a fabricated score", () => {
  const appeal = selectCollectorAppealBreakdown({
    publicRipContractV7: {
      collectorAppeal: {
        score: null,
        statusReason: "Collector Appeal V3 needs all three of D, F and P.",
        components: {},
      },
    },
  });
  assert.equal(appeal.available, false);
  assert.equal(appeal.score, null);
  assert.equal(appeal.scoreLabel, "—");
  assert.match(appeal.statusReason, /needs all three/);
  assert.match(componentSource, /data-collector-appeal-unavailable/);
});

test("the selector never falls back to a legacy model", () => {
  const code = stripComments(selectorSource.replace(/\/\*[\s\S]*?\*\//g, ""));
  for (const legacy of [
    /publicRipContractV6/,
    /overallRipV6/,
    /overallRipV5/,
    /legacyCollectorAppealCA7/,
    /collectorAppealV2/,
    /ripCore/,
    /openingExperience/,
    /universalSetDesirability/,
  ]) {
    assert.doesNotMatch(code, legacy, `the V3 selector must not read ${legacy}`);
  }
});

// --- Wiring and layout ------------------------------------------------------

test("the breakdown is mounted and fed the one resolved canonical bundle", () => {
  assert.match(pageSource, /import CollectorAppealBreakdown from "\.\/CollectorAppealBreakdown\.jsx";/);
  const start = pageSource.indexOf("function RipScoreBreakdownModule");
  const end = pageSource.indexOf("function StatTile", start);
  assert.ok(start >= 0 && end > start);
  const module = pageSource.slice(start, end);
  assert.match(module, /<CollectorAppealBreakdown/);
  // One prop: the bundle the hero and Financial RIP also read. Passing raw
  // sources here is what previously let this surface resolve independently and
  // land on a different source than the score above it.
  assert.match(module, /<CollectorAppealBreakdown canonical=\{canonical\}/);
  assert.doesNotMatch(module, /publicRipContractV6|overallRipV6/);
  assert.doesNotMatch(
    module,
    /<CollectorAppealBreakdown[^>]*publicRipContractV7=/,
    "the breakdown must take the resolved bundle, not a raw canonical source"
  );
});

test("publicRipContractV7 survives every allow-listing layer between API and page", () => {
  // The insights clients are ESM-syntax `.js` files this runner cannot import
  // by name, so they are asserted by source inspection, as elsewhere here.
  const criticalClient = fs
    .readFileSync(path.resolve(here, "../../lib/pokemon/pokemonSetInsightsCriticalClient.js"), "utf8")
    .replace(/\r\n/g, "\n");
  assert.match(criticalClient, /publicRipContractV7: toPlainObject\(payload\?\.publicRipContractV7\)/);
  assert.match(criticalClient, /overallRipV7: toPlainObject\(payload\?\.overallRipV7\)/);

  const criticalAdapter = pageSource.slice(
    pageSource.indexOf("function adaptPokemonSetInsightsCriticalPayloadToExplorePayload"),
    pageSource.indexOf("function adaptPokemonSetInsightsSecondaryPayloadToExplorePayload")
  );
  assert.match(criticalAdapter, /overallRipV7: critical\?\.overallRipV7/);
  assert.match(criticalAdapter, /publicRipContractV7: critical\?\.publicRipContractV7/);
});

test("the page resolves the canonical bundle once, without defaulting to a legacy model", () => {
  const start = pageSource.indexOf("const canonicalRip = useMemo(");
  assert.ok(start >= 0, "the page must resolve one canonical bundle");
  const block = pageSource.slice(start, start + 400);
  assert.match(block, /resolveCanonicalRipV7\(explorePayload, selectedTarget, summary\)/);
  assert.doesNotMatch(block, /overallRipV6/);
  assert.doesNotMatch(block, /overallRipV5/);
  assert.doesNotMatch(block, /ripCore/);

  // The defect this pass removed: three separate truthiness chains, one per
  // canonical object, each able to settle on a different source and each able
  // to be blocked by a normalized-but-truthy `{}`.
  for (const retired of [
    "const canonicalPublicRipContractV7 = useMemo(",
    "const canonicalOverallRipV7 = useMemo(",
    "const canonicalFinancialRipV3 = useMemo(",
  ]) {
    assert.equal(
      pageSource.includes(retired),
      false,
      `${retired} is a parallel resolution path and must not return`
    );
  }
});

test("Collector Appeal is presented exactly once on Insights", () => {
  const module = pageSource.slice(
    pageSource.indexOf("function RipScoreBreakdownModule"),
    pageSource.indexOf("function StatTile")
  );
  assert.equal((module.match(/<CollectorAppealBreakdown/g) || []).length, 1);
  assert.equal(
    (pageSource.match(/<CollectorAppealBreakdown/g) || []).length,
    1,
    "the component is mounted exactly once in the whole page"
  );
});

test("mobile and desktop layout contracts are preserved", () => {
  const grids = componentSource.match(/className="[^"]*grid[^"]*"/g) || [];
  assert.ok(grids.length > 0);
  for (const grid of grids) {
    assert.match(grid, /min-w-0|gap-/, `grid must be constrained: ${grid}`);
  }
  // Responsive, not a fixed multi-column row.
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
