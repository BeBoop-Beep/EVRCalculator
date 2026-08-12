// Financial RIP V3 breakdown — frontend contract tests.
//
// The claims under test:
//   * the six V3 cards render in the specified order,
//   * the legacy V2 view still renders its three pillars,
//   * no weighting percentage is shown on any V3 card,
//   * dollar values and ratios format correctly,
//   * missing data renders as an em dash and NEVER as 0,
//   * P95 copy says "begins at" (a threshold), not "average",
//   * the top-tail conditional mean is worded distinctly from the threshold,
//   * Depth and Robustness is not presented as a seventh weighted component,
//   * the layout contracts the surrounding page relies on are not broken.
//
// Structural assertions read the rendered JSX source, matching the existing
// contract tests for this page (the component tree cannot be imported outside
// the Next build). Value assertions run the real selectors.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  FINANCIAL_RIP_V3_CARD_ORDER,
  formatDollars,
  formatOneInN,
  formatPercent,
  formatRatio,
  selectDepthAndRobustness,
  selectFinancialRipV3Breakdown,
  selectFinancialRipV3DetailedMetrics,
} from "./financialRipV3Selector.mjs";
import { selectRipScoreBreakdown } from "./ripScoreBreakdownSelector.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
// The repo has mixed CRLF/LF in this directory; normalize before any
// multi-line or index-based source assertion.
const readSource = (name) =>
  fs.readFileSync(path.join(here, name), "utf8").replace(/\r\n/g, "\n");

const componentSource = readSource("FinancialRipV3Breakdown.jsx");
// The six components are drawn by the shared disclosure primitive, so some
// row-level guarantees are asserted against that file. Its rendered behaviour
// is covered by RipMetricDisclosureRow.test.jsx.
const rowComponentSource = readSource("RipMetricDisclosureRow.jsx");
const selectorSource = readSource("financialRipV3Selector.mjs");
const pageSource = readSource("RipStatisticsPageClient.jsx");

// Prose in these files legitimately NAMES the removed toggle and its labels
// while explaining why they were removed, so removal checks run against code.
const stripComments = (source) =>
  source
    .split("\n")
    .filter((line) => {
      const trimmed = line.trimStart();
      return !trimmed.startsWith("//") && !trimmed.startsWith("*") && !trimmed.startsWith("/*");
    })
    .join("\n");

// --- Fixture ---------------------------------------------------------------
// Shaped exactly like the backend `financialRipV3` object.

const V3_FIXTURE = {
  audit: { weights: { weights: {
    true_win_frequency: 0.25,
    typical_retention: 0.20,
    loss_resilience: 0.15,
    realistic_upside: 0.25,
    jackpot_upside: 0.10,
    base_economic_efficiency: 0.05,
  } } },
  score: 46.8,
  absoluteScore: 46.8,
  // Deliberately different from the absolute so an assertion can tell which
  // layer a surface read.
  relativeScore: 79.4,
  scoreVersion: "financial_rip_v3_outcome_profile_25_20_15_25_10_5",
  normalizationVersion: "financial_rip_v3_fixed_absolute_piecewise_v1",
  status: "ready",
  rankable: true,
  rank: 4,
  cohortSize: 21,
  components: {
    true_win_frequency: {
      score: 32.4,
      relativeScore: 58.2,
      rank: 6,
      tier: "B",
      cohortSize: 21,
      raw: { trueWinProbability: 0.0812, impliedOddsOneInN: 12.3, packCost: 4.99 },
    },
    typical_retention: {
      score: 24.1,
      relativeScore: 41.0,
      rank: 9,
      tier: "C",
      cohortSize: 21,
      raw: { typicalPackValue: 1.2, typicalRetentionRatio: 0.2405, packCost: 4.99 },
    },
    loss_resilience: {
      score: 30.7,
      relativeScore: 52.6,
      rank: 7,
      tier: "B",
      cohortSize: 21,
      raw: {
        averageLosingReturnValue: 1.31,
        averageRetentionGivenLoss: 0.2625,
        softLossShareGivenLoss: 0.1044,
        hardLossProbability: 0.8231,
        losingRunCount: 18_376,
      },
    },
    realistic_upside: {
      score: 61.9,
      relativeScore: 88.1,
      rank: 3,
      tier: "A",
      cohortSize: 21,
      raw: {
        p95ThresholdValue: 12.5,
        p95ThresholdRatio: 2.505,
        realisticTailMeanValue: 28.9,
        realisticTailMeanRatio: 5.792,
      },
    },
    jackpot_upside: {
      score: 74.2,
      relativeScore: 93.7,
      rank: 2,
      tier: "S",
      cohortSize: 21,
      raw: {
        p99ThresholdValue: 96.0,
        p99ThresholdRatio: 19.238,
        jackpotTailMeanValue: 310.4,
        jackpotTailMeanRatio: 62.204,
      },
    },
    base_economic_efficiency: {
      score: 41.0,
      relativeScore: 66.5,
      rank: 5,
      tier: "B",
      cohortSize: 21,
      raw: {
        totalRtpRatio: 0.94,
        baseRtpExcludingTop1Pct: 0.656,
        jackpotValueShare: 0.3021,
      },
    },
  },
  depthAndRobustness: {
    status: "ready",
    isWeighted: false,
    top1EvShare: 0.412,
    top2EvShare: 0.551,
    top3EvShare: 0.633,
    top5EvShare: 0.718,
    hhiEvConcentration: 0.2044,
    effectiveChaseCount: 4.9,
    cardsTracked: 34,
    totalCardEv: 5.9,
    jackpotValueShare: 0.3021,
    nonJackpotValueShare: 0.6979,
    concentrationTag: "moderately_concentrated",
    concentrationLabel: "Moderately concentrated",
  },
  distributionDisclosures: { p05Value: 0.24, p05IsScoredByV3: false },
};

const V2_FIXTURE = {
  financialRip: {
    components: {
      profit: { score: 61.1, rank: 2, tier: "A", cohortSize: 21, weight: 0.6, contribution: 36.66 },
      safety: { score: 22.6, rank: 14, tier: "D", cohortSize: 21, weight: 0.25, contribution: 5.65 },
      stability: { score: 26.5, rank: 11, tier: "C", cohortSize: 21, weight: 0.15, contribution: 3.98 },
    },
  },
};

// --- Card order -------------------------------------------------------------

test("the six V3 cards are defined in the specified order", () => {
  assert.deepEqual(FINANCIAL_RIP_V3_CARD_ORDER, [
    "Win Frequency",
    "Typical Retention",
    "Loss Resilience",
    // NOT the bare "Strong Upside" / "Jackpot Upside". Those are PUBLIC OUTCOME
    // METRICS with locked dollar definitions (the P95 and top-1% thresholds); a
    // normalized 0-100 component index must not share their names.
    "Strong Upside Quality",
    "Jackpot Upside Quality",
    "Base Economic Efficiency",
  ]);
});

test("the selector emits the six rows in that same order", () => {
  const { rows } = selectFinancialRipV3Breakdown(V3_FIXTURE);
  assert.equal(rows.length, 6);
  assert.deepEqual(
    rows.map((row) => row.title),
    FINANCIAL_RIP_V3_CARD_ORDER
  );
  assert.deepEqual(
    rows.map((row) => row.key),
    [
      "trueWinFrequency",
      "typicalRetention",
      "lossResilience",
      "realisticUpside",
      "jackpotUpside",
      "baseEconomicEfficiency",
    ]
  );
});

// --- Legacy V2 --------------------------------------------------------------

test("the legacy V2 view still renders exactly three pillars", () => {
  const { rows } = selectRipScoreBreakdown(V2_FIXTURE, {});
  assert.deepEqual(
    rows.map((row) => row.title),
    ["Profit", "Safety", "Stability"]
  );
  assert.deepEqual(
    rows.map((row) => row.score),
    [61.1, 22.6, 26.5]
  );
});

test("there is no model toggle: Financial RIP means V3 and nothing else", () => {
  // The public Current V3 / Legacy V2 switch is gone. Legacy V2 is still
  // computed and persisted on the backend for audit and rollback; it is simply
  // not a public presentation any more, so there is nothing to toggle between.
  const code = stripComments(componentSource);
  assert.doesNotMatch(code, /label:\s*"Current V3"/);
  assert.doesNotMatch(code, /label:\s*"Legacy V2"/);
  assert.doesNotMatch(code, /FINANCIAL_RIP_MODEL_MODES/);
  assert.doesNotMatch(code, /function ModelToggle/);
  assert.doesNotMatch(code, /function LegacyV2Cards/);
  assert.doesNotMatch(code, /"Legacy Financial RIP V2"/);
  // One heading, carrying the canonical name with no model version number.
  assert.match(code, />Financial RIP</);
  assert.doesNotMatch(code, /Financial RIP V3</);
});

// --- No visible weights -----------------------------------------------------

test("V3 component weights stay in the audit definition and never reach a public row", () => {
  // The weights are unchanged and still authoritative. They travel on the
  // backend object under `audit.weights.weights`, which is where audit,
  // Research and this test read them.
  assert.deepEqual(
    Object.values(V3_FIXTURE.audit.weights.weights),
    [0.25, 0.20, 0.15, 0.25, 0.10, 0.05]
  );

  // What changed is that the PUBLIC row model no longer carries one. These rows
  // are handed straight to the render layer, so a `weight` property on them is
  // one property access away from any render site — which is exactly how
  // `formatComponentMeta` came to print "· Weight 25%" beside a rank.
  const { rows } = selectFinancialRipV3Breakdown(V3_FIXTURE);
  for (const row of rows) {
    assert.equal("weight" in row, false, `${row.title} must not carry a weight`);
    assert.equal("contribution" in row, false, `${row.title} must not carry a contribution`);
  }

  // And nothing renders a weight or a composition share.
  assert.doesNotMatch(stripComments(componentSource), /Weight/);
  assert.doesNotMatch(stripComments(componentSource), /of Overall RIP/);
});

// --- Value formatting -------------------------------------------------------

test("dollar values, percentages and ratios format correctly", () => {
  assert.equal(formatDollars(12.5), "$12.50");
  assert.equal(formatDollars(310.4), "$310.40");
  assert.equal(formatPercent(0.0812), "8.1%");
  assert.equal(formatRatio(2.5), "2.50x");
  assert.equal(formatRatio(19.238), "19.24x");
  assert.equal(formatOneInN(12.3), "about 1 in 12 packs");
});

test("raw dollar values and ratios reach the rendered rows", () => {
  const { rows } = selectFinancialRipV3Breakdown(V3_FIXTURE);
  const byTitle = new Map(rows.map((row) => [row.title, row]));

  const typical = byTitle.get("Typical Retention").metrics;
  assert.equal(typical[0].value, "$1.20");
  assert.equal(typical[1].value, "24.1%");

  const jackpot = byTitle.get("Jackpot Upside Quality").metrics;
  assert.equal(jackpot[0].value, "$96.00");
  assert.equal(jackpot[1].value, "19.24x");
  assert.equal(jackpot[2].value, "$310.40");
});

// --- Missing data is never zero --------------------------------------------

test("missing data renders as an em dash, never as zero", () => {
  const empty = { status: "unavailable", components: {} };
  const { rows, diagnostics } = selectFinancialRipV3Breakdown(empty);
  assert.equal(diagnostics.status, "unavailable");
  for (const row of rows) {
    assert.equal(row.publicScore, null, `${row.title} public score must be null, not 0`);
    assert.equal(row.publicScoreLabel, "—");
    assert.equal(row.headline, "—", `${row.title} headline must be an em dash, not 0`);
    assert.equal(row.available, false);
    for (const metric of row.metrics) {
      assert.equal(metric.value, "—", `${row.title}/${metric.label} must not be 0`);
    }
  }
});

test("a genuine zero still renders as zero", () => {
  // Zero is a measurement. Only ABSENT data becomes an em dash.
  assert.equal(formatPercent(0), "0.0%");
  assert.equal(formatDollars(0), "$0.00");
  assert.equal(formatPercent(null), "—");
  assert.equal(formatDollars(undefined), "—");
});

test("the unavailable state never renders V2 numbers under the Financial RIP heading", () => {
  const start = componentSource.indexOf("data-v3-unavailable");
  assert.ok(start >= 0, "an explicit unavailable block must exist");
  const block = componentSource.slice(start, start + 1400);
  assert.match(block, /is not available for this set yet/);
  // There is no legacy selector left to read, and no offer to switch to one.
  assert.doesNotMatch(block, /v2\.rows\.map/);
  assert.doesNotMatch(block, /Legacy V2/);
  assert.doesNotMatch(stripComments(componentSource), /selectRipScoreBreakdown/);
});

test("the V3 selector has no fallback to V2 fields", () => {
  // The module's own prose explains WHY there is no fallback and legitimately
  // names the V2 fields, so the check runs against executable code only.
  const code = selectorSource
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !line.trimStart().startsWith("//"))
    .join("\n");
  assert.doesNotMatch(code, /ripCore/);
  assert.doesNotMatch(code, /\bprofit\b/i);
  assert.doesNotMatch(code, /\bsafetyScore\b/);
  assert.doesNotMatch(code, /stabilityScore/);
  const { fallbackUsed, diagnostics } = selectFinancialRipV3Breakdown(V3_FIXTURE);
  assert.equal(fallbackUsed, false);
  assert.equal(diagnostics.fallbackUsed, false);
});

// --- Copy precision ---------------------------------------------------------

test("P95 copy says the top 5% BEGINS at a value — never that it is an average", () => {
  const { rows } = selectFinancialRipV3Breakdown(V3_FIXTURE);
  const realistic = rows.find((row) => row.title === "Strong Upside Quality");
  const thresholdRow = realistic.metrics[0];
  assert.equal(thresholdRow.label, "Top 5% begins at");
  assert.doesNotMatch(thresholdRow.label, /average/i);
  // And the discredited "average one-in-20 return" phrasing appears nowhere.
  assert.doesNotMatch(selectorSource, /one[- ]in[- ]20/i);
});

test("the top-tail conditional mean is worded distinctly from the threshold", () => {
  const { rows } = selectFinancialRipV3Breakdown(V3_FIXTURE);
  const realistic = rows.find((row) => row.title === "Strong Upside Quality");
  const labels = realistic.metrics.map((metric) => metric.label);
  assert.ok(labels.includes("Top 5% begins at"));
  assert.ok(labels.includes("Average return, 95th–99th percentile"));
  // Two different numbers under two different labels.
  const threshold = realistic.metrics.find((m) => m.label === "Top 5% begins at").value;
  const mean = realistic.metrics.find((m) =>
    m.label.startsWith("Average return")
  ).value;
  assert.notEqual(threshold, mean);

  const jackpot = rows.find((row) => row.title === "Jackpot Upside Quality");
  const jackpotLabels = jackpot.metrics.map((metric) => metric.label);
  assert.ok(jackpotLabels.includes("Top 1% begins at"));
  assert.ok(jackpotLabels.includes("Average top 1% return"));
});

test("Loss Resilience copy never calls a loss a win", () => {
  const { rows } = selectFinancialRipV3Breakdown(V3_FIXTURE);
  const loss = rows.find((row) => row.title === "Loss Resilience");
  assert.doesNotMatch(loss.interpretation, /\bwin\b/i);
  for (const metric of loss.metrics) {
    assert.doesNotMatch(metric.label, /\bwin\b/i);
    assert.doesNotMatch(metric.label, /profit/i);
  }
  assert.deepEqual(
    loss.metrics.map((metric) => metric.value),
    ["$1.31", "26.3%", "10.4%", "82.3%"]
  );
});

test("Typical Retention copy says median or typical, never floor or minimum", () => {
  const { rows } = selectFinancialRipV3Breakdown(V3_FIXTURE);
  const typical = rows.find((row) => row.title === "Typical Retention");
  assert.match(typical.interpretation, /median/i);
  assert.doesNotMatch(typical.interpretation, /floor|minimum|guarantee/i);
});

// --- Depth and Robustness ---------------------------------------------------

test("Depth and Robustness is a separate unweighted diagnostic, not a seventh card", () => {
  const { rows } = selectFinancialRipV3Breakdown(V3_FIXTURE);
  assert.equal(rows.length, 6);
  assert.ok(!rows.some((row) => /depth|robustness|concentration/i.test(row.title)));

  const depth = selectDepthAndRobustness(V3_FIXTURE);
  assert.equal(depth.available, true);
  assert.equal(depth.isWeighted, false);
  assert.deepEqual(
    depth.rows.map((row) => row.label),
    ["Chase Depth", "Value Concentration", "Jackpot Dependence", "Number of Effective Chases"]
  );
  // Rendered BELOW the six scored rows, behind its own collapsed disclosure,
  // and explicitly marked as context rather than a seventh scored component.
  assert.match(componentSource, /Additional context — not part of the Financial RIP score\./);
  assert.match(componentSource, /data-depth-and-robustness-context-only="true"/);
  // It does not borrow the scored-row component, which would put it in the
  // same visual class as the six things that ARE scored.
  const depthPanel = componentSource.slice(
    componentSource.indexOf("function DepthAndRobustnessPanel"),
    componentSource.indexOf("// `canonical` is the ALREADY-RESOLVED bundle")
  );
  assert.doesNotMatch(depthPanel, /<RipMetricDisclosureRow/);
  // And it renders after the six rows in the tree, not among them.
  assert.ok(
    componentSource.indexOf("data-financial-rip-rows") <
      componentSource.indexOf("<DepthAndRobustnessPanel")
  );
});

test("Depth and Robustness reports unavailable rather than zero", () => {
  const depth = selectDepthAndRobustness({ depthAndRobustness: { status: "unavailable" } });
  assert.equal(depth.available, false);
  for (const row of depth.rows) {
    assert.equal(row.value, "—");
  }
});

// --- Detailed metrics -------------------------------------------------------

test("the detailed metrics add the conditional tail averages and the loss profile", () => {
  const metrics = selectFinancialRipV3DetailedMetrics(V3_FIXTURE);
  const byKey = new Map(metrics.map((metric) => [metric.key, metric]));
  assert.equal(byKey.get("realisticTailMean").value, "$28.90");
  assert.equal(byKey.get("jackpotTailMean").value, "$310.40");
  assert.equal(byKey.get("averageLosingReturn").value, "$1.31");
  assert.equal(byKey.get("hardLossProbability").value, "82.3%");
  assert.equal(byKey.get("baseRtp").value, "65.6%");
});

test("P05 is still shown in the detailed metrics and is labelled honestly", () => {
  const metrics = selectFinancialRipV3DetailedMetrics(V3_FIXTURE);
  const p05 = metrics.find((metric) => metric.key === "p05Value");
  assert.ok(p05, "P05 must remain visible");
  assert.equal(p05.value, "$0.24");
  assert.equal(p05.label, "5th percentile pack value");
});

// --- Layout contracts -------------------------------------------------------

test("the breakdown is mounted inside the RIP Score Breakdown module", () => {
  assert.match(pageSource, /import FinancialRipV3Breakdown from "\.\/FinancialRipV3Breakdown\.jsx";/);
  const start = pageSource.indexOf("function RipScoreBreakdownModule");
  const end = pageSource.indexOf("function StatTile", start);
  assert.ok(start >= 0 && end > start);
  const module = pageSource.slice(start, end);
  assert.match(module, /<FinancialRipV3Breakdown/);
  // One prop: the same resolved bundle the hero and Collector Appeal read.
  assert.match(module, /<FinancialRipV3Breakdown canonical=\{canonical\}/);
  // No raw canonical source and no legacy object reaches the component at all.
  assert.doesNotMatch(module, /<FinancialRipV3Breakdown[^>]*financialRipV3=/);
  assert.doesNotMatch(module, /legacyRip=/);
});

test("the page resolves the canonical bundle once, without defaulting to ripCore", () => {
  const start = pageSource.indexOf("const canonicalRip = useMemo(");
  assert.ok(start >= 0, "the page must resolve one canonical bundle");
  const block = pageSource.slice(start, start + 400);
  assert.match(block, /resolveCanonicalRipV7\(explorePayload, selectedTarget, summary\)/);
  assert.doesNotMatch(block, /ripCore/);
});

test("financialRipV3 survives every allow-listing layer between API and page", async () => {
  // Both the client normalizers and the page adapters allow-list keys, so a new
  // backend field is dropped silently unless every layer names it. This walks
  // the real chain: backend JSON -> normalizer -> page adapter.
  const backendPayload = {
    set: { id: "s1", name: "Perfect Order", slug: "perfectOrder" },
    summary: {},
    interpretation: {},
    rip: { score: 49.0 },
    ripCore: { score: 46.4 },
    financialRipV3: V3_FIXTURE,
    overallRipV5: { score: 36.6, version: "overall_rip_v5_90_financial_v3_10_ca7" },
    publicRipContractV5: { contractVersion: "public_rip_contract_v5" },
    meta: { warnings: [] },
  };

  const { normalizePokemonSetInsightsCriticalPayload } = await import(
    "../../lib/pokemon/pokemonSetInsightsCriticalClient.js"
  );
  const normalized = normalizePokemonSetInsightsCriticalPayload(backendPayload);
  assert.equal(normalized.financialRipV3.score, 46.8, "the normalizer must keep financialRipV3");
  assert.ok(normalized.overallRipV5, "the normalizer must keep overallRipV5");
  assert.ok(normalized.publicRipContractV5, "the normalizer must keep publicRipContractV5");

  // The page adapter is inside the un-importable client module, so its field
  // list is asserted from source.
  const criticalAdapter = pageSource.slice(
    pageSource.indexOf("function adaptPokemonSetInsightsCriticalPayloadToExplorePayload"),
    pageSource.indexOf("function adaptPokemonSetInsightsSecondaryPayloadToExplorePayload")
  );
  assert.match(criticalAdapter, /financialRipV3: critical\?\.financialRipV3/);
  assert.match(criticalAdapter, /overallRipV5: critical\?\.overallRipV5/);

  const fullAdapter = pageSource.slice(
    pageSource.indexOf("function adaptPokemonSetInsightsPayloadToExplorePayload"),
    pageSource.indexOf("// Progressive-rendering split of the adapter above")
  );
  assert.match(fullAdapter, /financialRipV3: normalized\?\.financialRipV3/);

  // And the selector renders the object that survived the chain.
  const { rows, diagnostics } = selectFinancialRipV3Breakdown(normalized.financialRipV3);
  assert.equal(diagnostics.status, "ready");
  assert.equal(rows[0].publicScoreLabel, "58.2");
});

test("mobile and desktop layout contracts are preserved", () => {
  // Every container must be min-w-0 so a long value cannot force the page to
  // scroll horizontally — the contract the surrounding sections rely on.
  const containers = componentSource.match(/className="[^"]*(?:grid|flex(?![-\w]))[^"]*"/g) || [];
  assert.ok(containers.length > 0);
  for (const container of containers) {
    assert.match(container, /min-w-0|gap-/, `container must be constrained: ${container}`);
  }
  // The six components are a stack of rows, not a card grid; the row itself
  // carries the min-w-0 and tabular-nums contract.
  assert.match(componentSource, /data-financial-rip-rows className="mt-2 min-w-0"/);
  assert.match(rowComponentSource, /min-w-0/);
  assert.match(rowComponentSource, /tabular-nums/);
});

test("the six components render as six disclosure rows, one per canonical component", () => {
  const { rows } = selectFinancialRipV3Breakdown(V3_FIXTURE);
  assert.equal(rows.length, 6, "exactly six scored components");

  // One row element per selector row, keyed by the canonical component key, and
  // drawn by the SAME component Collector Appeal's factors use.
  assert.match(componentSource, /\{v3\.rows\.map\(\(row\) => \(/);
  assert.match(componentSource, /<RipMetricDisclosureRow/);
  assert.match(componentSource, /rowKey=\{row\.key\}/);
  assert.match(componentSource, /dataAttribute="data-v3-component"/);
  // Every supporting metric is handed to the row, so nothing is dropped in
  // exchange for the shorter default view.
  assert.match(componentSource, /metrics=\{row\.metrics\}/);
  // Tier and rank still reach the row, from backend fields only.
  assert.match(componentSource, /meta=\{formatComponentMeta\(row\)\}/);
});
