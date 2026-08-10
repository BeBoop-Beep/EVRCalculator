// Insights redesign pass — frontend contract tests.
//
// WHAT THIS FILE GUARDS
// ---------------------
// The set-page Insights redesign is a PRESENTATION change. Its whole risk
// surface is that a visual pass quietly changes what is claimed: a new bar
// invents a number, a "premium" treatment leaks onto the header or onto every
// row, a grid drops a canonical component, or an unavailable metric starts
// drawing an empty fill that reads as a real zero. Each of those is asserted
// here, and the two rules that carry the art direction are asserted as an
// exclusive pair:
//
//   ELEVATED rails exist on exactly THREE elements — the Insights Summary's
//   RIP Score, Financial RIP and Collector Appeal cards.
//   QUIET rails are what every breakdown row gets, and they must carry no
//   glow, no bloom shadow and no end-cap dot.
//
// Rendering assertions mount the real components with react-test-renderer.
// Source assertions are used only where a component cannot be mounted outside
// the Next build (the 670KB page client), matching the existing contract tests
// in this directory.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import React from "react";
import TestRenderer from "react-test-renderer";

import InsightsSummaryModule from "./InsightsSummaryModule.jsx";
import RipMetricDisclosureRow from "./RipMetricDisclosureRow.jsx";
import { RIP_SUMMARY_DESCRIPTIONS } from "./OverviewRipSummary.jsx";
import { selectCollectorAppealBreakdown } from "./collectorAppealBreakdownSelector.mjs";
import { selectFinancialRipV3Breakdown } from "./financialRipV3Selector.mjs";
import { resolveNextOpenKeys } from "./ripDisclosurePolicy.mjs";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const here = path.dirname(fileURLToPath(import.meta.url));
// Mixed CRLF/LF lives in this directory; normalize before any source assertion.
const readSource = (name) => fs.readFileSync(path.join(here, name), "utf8").replace(/\r\n/g, "\n");

const pageSource = readSource("RipStatisticsPageClient.jsx");
const summarySource = readSource("InsightsSummaryModule.jsx");
const rowSource = readSource("RipMetricDisclosureRow.jsx");
const financialSource = readSource("FinancialRipV3Breakdown.jsx");
const collectorSource = readSource("CollectorAppealBreakdown.jsx");

const stripComments = (source) =>
  source
    .split("\n")
    .filter((line) => {
      const trimmed = line.trimStart();
      return !trimmed.startsWith("//") && !trimmed.startsWith("*") && !trimmed.startsWith("/*");
    })
    .join("\n");

// The whole-page section the redesign owns. Everything outside it is out of
// scope for this pass and is asserted as UNCHANGED further down.
const insightsSection = pageSource.slice(
  pageSource.indexOf("function RipScoreBreakdownModule("),
  pageSource.indexOf("function StatTile(")
);

// --- Fixtures ---------------------------------------------------------------

const V7_FIXTURE = {
  contractVersion: "public_rip_contract_v7",
  overallRip: { score: 57.75, absoluteScore: 57.75, relativeScore: 73.4, rank: 4, rankedSetCount: 21, tier: "A" },
  financialRip: {
    score: 46.8,
    rank: 4,
    rankedSetCount: 21,
    tier: "B",
    status: "ready",
    components: {
      trueWinFrequency: { score: 32.4, rank: 6, tier: "B", rankedSetCount: 21, raw: {} },
      typicalRetention: { score: 24.1, rank: 9, tier: "C", rankedSetCount: 21, raw: {} },
      lossResilience: { score: 30.7, rank: 7, tier: "B", rankedSetCount: 21, raw: {} },
      realisticUpside: { score: 61.9, rank: 3, tier: "A", rankedSetCount: 21, raw: {} },
      jackpotUpside: { score: 55.2, rank: 5, tier: "B", rankedSetCount: 21, raw: {} },
      baseEconomics: { score: 41.0, rank: 8, tier: "C", rankedSetCount: 21, raw: {} },
    },
  },
  collectorAppeal: {
    score: 65.6858,
    relativeScore: 70.1,
    rank: 3,
    rankedSetCount: 21,
    tier: "A",
    weightsDisclosed: false,
    components: {
      rosterDesirability: { score: 62.0, rawValue: 0.62 },
      desirableOutcomeFrequency: { rawValue: 0.031, impliedOddsOneInN: 32.26, eligibleCardCount: 24 },
      dualPathDepth: { rawValue: 0.4385, subjectsWithMultiplePaths: 5 },
    },
    subjectScope: {
      modeled: ["Pokémon"],
      notYetModeled: ["Trainer", "Artist"],
      note: "Trainer and artist desirability are not yet modeled. They are omitted from this metric rather than scored as zero.",
    },
  },
};

const CANONICAL = { publicRipContractV7: V7_FIXTURE };

function renderSummary(props = {}) {
  let renderer;
  TestRenderer.act(() => {
    renderer = TestRenderer.create(
      React.createElement(InsightsSummaryModule, {
        canonical: CANONICAL,
        overallScore: 73.4,
        overallTier: "A",
        overallRank: 4,
        overallCohortSize: 21,
        ...props,
      })
    );
  });
  return renderer;
}

const findAllBy = (renderer, attribute) =>
  renderer.root.findAll((node) => node.props?.[attribute] !== undefined);

function textOf(node) {
  const collected = [];
  const walk = (value) => {
    if (value === null || value === undefined || value === false) return;
    if (typeof value === "string" || typeof value === "number") {
      collected.push(String(value));
      return;
    }
    if (Array.isArray(value)) {
      value.forEach(walk);
      return;
    }
    // Handles both a rendered JSON tree ({ type, props, children }) and a
    // TestInstance ({ props, children }), so one helper reads either.
    if (value.children) walk(value.children);
    else if (value.props) walk(value.props.children);
  };
  walk(node);
  return collected.join(" ");
}

// --- TASK 1: the Insights Summary -------------------------------------------

test("the Insights Summary is one grouped surface carrying exactly three canonical metrics", () => {
  const renderer = renderSummary();
  const cards = findAllBy(renderer, "data-insights-summary-metric");
  assert.deepEqual(
    cards.map((card) => card.props["data-insights-summary-metric"]),
    ["overall", "financial", "collector"],
    "exactly RIP Score, Financial RIP and Collector Appeal, in that order"
  );

  const text = textOf(renderer.toJSON());
  for (const label of ["RIP Score", "Financial RIP", "Collector Appeal"]) {
    assert.ok(text.includes(label), `${label} must be labelled`);
  }
  // The three neutral explanations are the ones Overview already publishes,
  // imported rather than restated, so the two surfaces cannot drift.
  assert.match(summarySource, /import \{ RIP_SUMMARY_DESCRIPTIONS \} from "\.\/OverviewRipSummary\.jsx";/);
  for (const description of Object.values(RIP_SUMMARY_DESCRIPTIONS)) {
    assert.ok(text.includes(description), `missing summary copy: ${description}`);
  }
  // ...and it must not restate them as its own literals.
  assert.equal(stripComments(summarySource).includes("Monetary pack outcomes compared with pack cost."), false);
});

test("the summary prints the backend's own numbers and never computes one", () => {
  const text = textOf(renderSummary().toJSON());
  assert.ok(text.includes("73.4"), "the Overall RIP relative score, as handed down by the page");
  assert.ok(text.includes("46.8"), "Financial RIP V3's canonical fixed-anchor score");
  assert.ok(text.includes("65.7"), "Collector Appeal V3's canonical score");
  assert.ok(text.includes("Rank #4 of 21"));
  assert.ok(text.includes("A Tier"));
  // No arithmetic on scores anywhere in the module: no blend, no weighting, no
  // reconstruction of a composition.
  const code = stripComments(summarySource);
  // Colour alphas legitimately contain decimals, so this looks for the shape of
  // a blend instead: a score multiplied or added into another score, or any
  // read of the withheld weight vector.
  assert.doesNotMatch(code, /weightsDisclosed|weights\b|contribution/i, "no weight or contribution is read");
  assert.doesNotMatch(code, /[Ss]core\s*[*+]|[*+]\s*\w*[Ss]core/, "no score is blended, weighted or summed here");
  assert.doesNotMatch(code, /ripCore|overallRipV6|overallRipV5|overallRipV4|financialRipV2|collectorAppealV2/i);
});

test("a missing metric renders an em dash, never a zero", () => {
  const renderer = renderSummary({ canonical: null, overallScore: null });
  const scores = findAllBy(renderer, "data-insights-summary-score").map((node) => textOf(node));
  assert.deepEqual(scores, ["—", "—", "—"], "every unavailable metric prints an em dash");
  const text = textOf(renderer.toJSON());
  assert.ok(text.includes("Not available for this set yet."));
  assert.equal(/\b0\.0\b/.test(text), false, "no zero may be substituted for a missing score");

  // And an unavailable metric draws an EMPTY track, not a zero-length fill —
  // a fill of any width is a claim about a value that does not exist.
  const rails = findAllBy(renderer, "data-insights-summary-rail");
  assert.equal(rails.length, 3);
  for (const rail of rails) {
    assert.equal(rail.props["data-rail-available"], "false");
    assert.equal(rail.children.length, 0, "an unavailable rail renders no fill at all");
  }
});

// --- TASK 8: the bar / rail / glow rules ------------------------------------

test("exactly three rails carry the elevated treatment, and they are the summary's", () => {
  const rails = findAllBy(renderSummary(), "data-insights-summary-rail");
  assert.equal(rails.length, 3, "one elevated rail per summary card, and no more");
  for (const rail of rails) {
    assert.equal(rail.props["data-rail-emphasis"], "elevated");
    assert.equal(rail.props["data-rail-available"], "true");
    const [fill] = rail.children;
    // A gradual left-to-right bloom: the gradient gains luminance toward the
    // leading edge, and the soft shadow is in the same hue.
    assert.match(fill.props.style.background, /linear-gradient\(90deg/);
    assert.match(fill.props.style.boxShadow, /0 0 10px/, "the elevated rail keeps its soft bloom");
  }

  // The elevated treatment exists in ONE file. No breakdown surface may import
  // or re-declare it.
  for (const [name, source] of [
    ["RipMetricDisclosureRow.jsx", rowSource],
    ["FinancialRipV3Breakdown.jsx", financialSource],
    ["CollectorAppealBreakdown.jsx", collectorSource],
  ]) {
    assert.equal(source.includes('data-rail-emphasis="elevated"'), false, `${name} must not use the elevated rail`);
    assert.equal(source.includes("SummaryRail"), false, `${name} must not borrow the summary rail`);
  }
});

test("breakdown rails are quiet: no bloom, no shadow, no end cap", () => {
  let renderer;
  TestRenderer.act(() => {
    renderer = TestRenderer.create(
      React.createElement(RipMetricDisclosureRow, {
        rowKey: "trueWinFrequency",
        title: "Chance to Win",
        value: "72.1",
        railPercent: 72.1,
        accentFamily: "financial",
        metrics: [{ label: "Pack price used", value: "$4.49" }],
      })
    );
  });

  const [rail] = findAllBy(renderer, "data-rip-metric-rail");
  assert.ok(rail, "a scored row draws a rail");
  assert.equal(rail.props["data-rail-emphasis"], "quiet");
  const [fill] = rail.children;
  assert.equal(fill.props.style.width, "72.1%");
  assert.equal(fill.props.style.boxShadow, undefined, "a quiet rail carries no glow");
  assert.equal(fill.children.length, 0, "a quiet rail carries no end-cap dot");
  // The quiet rail is thinner and sits on a fainter track than the elevated one.
  assert.match(rail.props.className, /h-1\b/);
  assert.match(summarySource, /data-insights-summary-rail[\s\S]{0,400}h-1\.5/);
});

test("an unavailable breakdown metric draws an empty track rather than a zero fill", () => {
  let renderer;
  TestRenderer.act(() => {
    renderer = TestRenderer.create(
      React.createElement(RipMetricDisclosureRow, {
        rowKey: "dualPathDepth",
        title: "Dual-Path Depth",
        value: "—",
        railPercent: null,
        accentFamily: "collector",
      })
    );
  });
  assert.equal(findAllBy(renderer, "data-rip-metric-rail").length, 0, "no rail at all when there is no value");
  assert.ok(textOf(renderer.toJSON()).includes("—"));
});

test("each section's rails use its own accent family and nothing else", () => {
  const railAccents = /const RAIL_ACCENTS = \{([\s\S]*?)\};/.exec(rowSource);
  assert.ok(railAccents, "the row declares its two accent families");
  assert.match(railAccents[1], /financial:/);
  assert.match(railAccents[1], /collector:/);
  assert.equal((railAccents[1].match(/:/g) || []).length, 2, "exactly two families - no per-card palette");

  assert.match(financialSource, /accentFamily="financial"/);
  assert.match(collectorSource, /accentFamily="collector"/);
  assert.equal(financialSource.includes('accentFamily="collector"'), false);
  assert.equal(collectorSource.includes('accentFamily="financial"'), false);
});

test("no rail, anywhere in Insights, is drawn from anything but a real backend value", () => {
  // Financial rows pass the component's own backend score; Collector rows pass
  // the selector's presentation-only reading of the value already on the row.
  assert.match(financialSource, /railPercent=\{row\.available \? row\.score : null\}/);
  assert.match(collectorSource, /railPercent=\{row\.railPercent \?\? null\}/);
  for (const source of [summarySource, rowSource, financialSource, collectorSource]) {
    const code = stripComments(source);
    assert.doesNotMatch(code, /Math\.random|placeholder|dummyData|fakeSeries/i);
  }
});

// --- TASK 2 / 8D: no gamification, no fake charts ---------------------------

test("Insights renders no sparkline, no fabricated history and no achievement chrome", () => {
  for (const [name, source] of [
    ["InsightsSummaryModule.jsx", summarySource],
    ["RipMetricDisclosureRow.jsx", rowSource],
    ["FinancialRipV3Breakdown.jsx", financialSource],
    ["CollectorAppealBreakdown.jsx", collectorSource],
  ]) {
    const code = stripComments(source);
    assert.doesNotMatch(code, /Sparkline|<polyline|<path\b|LineChart|AreaChart/, `${name} must draw no chart`);
    assert.doesNotMatch(code, /badge-xl|trophy|achievement|streak/i, `${name} must carry no achievement chrome`);
  }
  // The optional chip-based "what this pack is good at" strengths UI is not on
  // the page at all.
  assert.equal(/what this pack is good at/i.test(pageSource), false);
});

// --- TASKS 3 / 6: the canonical taxonomy survives the layout change ---------

test("Financial RIP still renders exactly its six canonical components", () => {
  const { rows } = selectFinancialRipV3Breakdown(V7_FIXTURE.financialRip);
  assert.deepEqual(rows.map((row) => row.title), [
    "Chance to Win",
    "Typical Opening",
    "Loss Resilience",
    "Strong Upside",
    "Jackpot Upside",
    "Base Economics",
  ]);
  // One mapped row element, so a grid cannot introduce or drop a component.
  assert.equal((financialSource.match(/<RipMetricDisclosureRow/g) || []).length, 1);
  assert.match(financialSource, /\{v3\.rows\.map\(\(row\) => \(/);
});

test("Collector Appeal still renders exactly its three canonical factors", () => {
  const appeal = selectCollectorAppealBreakdown(CANONICAL);
  assert.deepEqual(appeal.rows.map((row) => row.title), [
    "Roster Desirability",
    "Desirable Outcome Frequency",
    "Dual-Path Depth",
  ]);
  assert.equal((collectorSource.match(/<RipMetricDisclosureRow/g) || []).length, 1);
});

test("the desktop grids cannot clip an expanded panel", () => {
  for (const [name, source] of [
    ["FinancialRipV3Breakdown.jsx", financialSource],
    ["CollectorAppealBreakdown.jsx", collectorSource],
  ]) {
    assert.match(source, /desk:grid-cols-3/, `${name} lays its cards out on a desktop grid`);
    assert.match(source, /items-start/, `${name} must not stretch an expanded cell`);
    assert.doesNotMatch(source, /max-h-|overflow-hidden|h-\[\d/, `${name} must not fix a cell's height`);
  }
});

test("supporting metrics survive the redesign and stay behind a truthful disclosure", () => {
  const METRICS = [
    { label: "Chance to recover cost", value: "38.4%" },
    { label: "Pack price used", value: "$4.49" },
  ];
  let renderer;
  TestRenderer.act(() => {
    renderer = TestRenderer.create(
      React.createElement(RipMetricDisclosureRow, {
        rowKey: "trueWinFrequency",
        title: "Chance to Win",
        value: "72.1",
        railPercent: 72.1,
        accentFamily: "financial",
        metrics: METRICS,
        isOpen: true,
      })
    );
  });
  const text = textOf(renderer.toJSON());
  for (const metric of METRICS) {
    assert.ok(text.includes(metric.label), `${metric.label} must still be reachable`);
    assert.ok(text.includes(metric.value));
  }
  const [button] = renderer.root.findAll((node) => node.type === "button");
  assert.equal(button.props["aria-expanded"], true);
  assert.ok(button.props["aria-controls"], "the control names its panel");
  const [panel] = renderer.root.findAll((node) => node.props?.role === "region");
  assert.equal(panel.props.id, button.props["aria-controls"], "aria-controls resolves to the panel");
});

// --- TASKS 4 / 7: mobile disclosure behaviour -------------------------------

test("mobile keeps one open row per section, and the two sections stay independent", () => {
  // The policy is a decision, tested as one. Financial and Collector each call
  // useRipDisclosureSection separately, so they hold separate open sets.
  assert.deepEqual(
    resolveNextOpenKeys(["chanceToWin"], "typicalReturn", { isDesktop: false }),
    ["typicalReturn"],
    "below desktop, opening a row closes the previous one"
  );
  assert.deepEqual(
    resolveNextOpenKeys(["chanceToWin"], "typicalReturn", { isDesktop: true }).sort(),
    ["chanceToWin", "typicalReturn"],
    "desktop may compare two components side by side"
  );
  for (const source of [financialSource, collectorSource]) {
    assert.match(source, /const disclosure = useRipDisclosureSection\(\);/);
    assert.match(source, /isOpen=\{disclosure\.openKeys\.includes\(row\.key\)\}/);
    assert.match(source, /onToggle=\{disclosure\.toggle\}/);
  }
});

test("the Desirable Outcome Frequency caveat is visible without expanding anything", () => {
  const appeal = selectCollectorAppealBreakdown(CANONICAL);
  const frequency = appeal.rows.find((row) => row.key === "desirableOutcomeFrequency");
  assert.equal(frequency.disclaimer, "A desirable outcome can still be worth less than the pack price.");

  let renderer;
  TestRenderer.act(() => {
    renderer = TestRenderer.create(
      React.createElement(RipMetricDisclosureRow, {
        rowKey: frequency.key,
        title: frequency.title,
        value: frequency.value,
        railPercent: frequency.railPercent,
        accentFamily: "collector",
        disclaimer: frequency.disclaimer,
        metrics: frequency.metrics,
        isOpen: false,
      })
    );
  });
  assert.ok(textOf(renderer.toJSON()).includes(frequency.disclaimer), "the caveat survives a collapse");
});

test("the trainer/artist limitation is stated exactly once", () => {
  const appeal = selectCollectorAppealBreakdown(CANONICAL);
  assert.match(appeal.subjectScope.note, /Trainer and artist desirability are not yet modeled/);
  assert.equal(
    (collectorSource.match(/subjectScope\.note/g) || []).length,
    1,
    "one render site for the limitation"
  );
  assert.equal(
    /Trainer and artist desirability/.test(stripComments(summarySource) + stripComments(financialSource)),
    false,
    "no other Insights surface may restate it"
  );
});

// --- TASK 5: Depth and Robustness stays context only ------------------------

test("Depth and Robustness is context, collapsed by default, and not a seventh metric", () => {
  assert.match(financialSource, /data-depth-and-robustness-context-only="true"/);
  assert.match(financialSource, /Additional context — not part of the Financial RIP score\./);
  assert.match(financialSource, /const \[isOpen, setIsOpen\] = useState\(false\);/);
  // It must not borrow the scored-row primitive, and it must not draw a rail —
  // either would put it in the same visual class as the six scored components.
  const depth = financialSource.slice(
    financialSource.indexOf("function DepthAndRobustnessPanel"),
    financialSource.indexOf("export default function FinancialRipV3Breakdown")
  );
  assert.equal(depth.includes("<RipMetricDisclosureRow"), false);
  assert.equal(depth.includes("railPercent"), false);
});

// --- TASKS 9 / 12: scope boundaries -----------------------------------------

test("the mobile Insights tab treatment is opt-in, mobile-only and used by one caller", () => {
  const tabs = pageSource.slice(
    pageSource.indexOf("function SectionViewTabs("),
    pageSource.indexOf("function getSimpleAverageLossValue(")
  );
  const emphasis = /const mobileEmphasisClass =([\s\S]*?);\n/.exec(tabs);
  assert.ok(emphasis, "the emphasis class is computed in one place");
  // EVERY utility it adds is max-desk-scoped, so 1200px+ renders unchanged CSS.
  const utilities = (emphasis[1].match(/"([^"]*)"/g) || [])
    .join(" ")
    .split(/\s+/)
    .filter((token) => token && token !== '""');
  assert.ok(utilities.length > 0);
  for (const utility of utilities) {
    assert.match(utility.replace(/"/g, ""), /^max-desk:/, `desktop tabs must not change: ${utility}`);
  }
  // Active-only, and only for the option the caller named.
  assert.match(emphasis[1], /isActive && mobileEmphasisValue && option\.value === mobileEmphasisValue/);
  // Exactly one caller opts in, and it opts in to "insights".
  const callers = pageSource.match(/mobileEmphasisValue="[^"]*"/g) || [];
  assert.deepEqual(callers, ['mobileEmphasisValue="insights"'], "no other segmented control is restyled");
  // The pre-existing active/inactive branch is byte-identical.
  assert.ok(
    tabs.includes(
      '"bg-[linear-gradient(135deg,rgba(16,185,129,0.95),rgba(20,184,166,0.78))] text-white shadow-[0_4px_12px_rgba(20,184,166,0.18),inset_0_1px_0_rgba(255,255,255,0.16)]"'
    ),
    "the existing active treatment is untouched"
  );
  assert.ok(
    tabs.includes('"bg-transparent text-[color:color-mix(in_srgb,var(--text-secondary)_82%,transparent)] hover:bg-[rgba(255,255,255,0.045)] hover:text-[var(--text-primary)]"'),
    "inactive tabs stay subdued and untouched"
  );
  // Behaviour, order and accessibility are preserved.
  assert.match(tabs, /aria-pressed=\{isActive\}/);
  assert.match(tabs, /onClick=\{\(\) => onChange\(option\.value\)\}/);
  const tabList = pageSource.slice(pageSource.indexOf('mobileEmphasisValue="insights"'), pageSource.indexOf('mobileEmphasisValue="insights"') + 500);
  assert.match(tabList, /"overview"[\s\S]*"cards"[\s\S]*"pull-rates"[\s\S]*"insights"/, "tab order is unchanged");
});

test("the set header is untouched by this pass", () => {
  // The redesign lives inside RipScoreBreakdownModule. None of the header's
  // structures may appear there, and the header's own contracts still hold.
  assert.equal(/data-set-context-header/.test(insightsSection), false);
  assert.equal(/PokemonSetMobileHero|data-set-sticky-picker|SetPageNavigationRail/.test(insightsSection), false);
  assert.ok(pageSource.includes('data-set-context-shell className="set-detail-context-shell overflow-visible'));
  assert.ok(pageSource.includes("data-set-context-header"));
  assert.ok(pageSource.includes("<PokemonSetMobileHero"));
  // The summary module is mounted in Insights only, exactly once.
  assert.equal((pageSource.match(/<InsightsSummaryModule/g) || []).length, 1);
  assert.ok(insightsSection.includes("<InsightsSummaryModule"));
  // Overview keeps ITS summary, unchanged and un-elevated.
  assert.ok(pageSource.includes("<OverviewRipSummary"));
  assert.equal(readSource("OverviewRipSummary.jsx").includes("data-rail-emphasis"), false);
});

test("every Insights surface reads the one resolved canonical bundle", () => {
  assert.ok(insightsSection.includes("<FinancialRipV3Breakdown canonical={canonical}"));
  assert.ok(insightsSection.includes("<CollectorAppealBreakdown canonical={canonical} />"));
  assert.ok(insightsSection.includes("<InsightsSummaryModule"));
  assert.match(insightsSection, /canonical=\{canonical\}[\s\S]{0,400}overallScore=\{score\}/);
  // The Overall values are handed down from the page's single hero selection
  // rather than resolved a second time, so Insights cannot disagree with the
  // sticky header for the same set.
  assert.equal(summarySource.includes("readCanonicalBlock"), false);
  assert.match(pageSource, /overallBadges=\{<HeroScoreBadges rank=\{rankValue\} tier=\{rankTier\} cohortSize=\{cohortSize\} \/>\}/);
});

test("no weight, formula, contribution, legacy toggle or retired verdict copy returns", () => {
  const surfaces = [summarySource, rowSource, financialSource, collectorSource].map(stripComments).join("\n");
  for (const forbidden of [
    /Contributes /,
    /formatWeightPercent/,
    /RIP Core/,
    /Legacy V2/,
    /Opening Outlook/,
    /Decision Signals/,
    /Chase Potential/,
    /Opening Experience/,
    /% of Overall RIP/,
  ]) {
    assert.doesNotMatch(surfaces, forbidden, `retired presentation returned: ${forbidden}`);
  }
  // No version number is published in user-facing copy on any Insights surface.
  assert.doesNotMatch(surfaces, />\s*[^<]*\bV[2-7]\b/);
});
