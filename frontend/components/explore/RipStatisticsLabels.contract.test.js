const fs = require("fs");
const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");

const ripPageClientPath = path.resolve(__dirname, "RipStatisticsPageClient.jsx");
const historyChartPath = path.resolve(__dirname, "PackValueHistoryChart.jsx");
const distributionChartPath = path.resolve(__dirname, "RipDistributionChart.jsx");
const performanceFormattingPath = path.resolve(__dirname, "performanceVsCostFormatting.mjs");
const rankingConfigPath = path.resolve(__dirname, "../../constants/exploreRankingConfig.js");

test("Set Intelligence Biggest Upside wiring references relative-first score fields and both upside evidence labels", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes('scoreFields: ["relative_biggest_upside_score", "biggest_upside_score"]'));
  assert.ok(source.includes('tierField: "biggest_upside_tier"'));
  assert.ok(source.includes('rankField: "biggest_upside_rank"'));
  assert.ok(source.includes('"Realistic Upside"'));
  assert.ok(source.includes('"God Pull Upside"'));
});

test("Set Intelligence Expected Value wiring prefers relative score fields", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes('"relative_average_return_score"'));
  assert.ok(source.includes('"relative_mean_value_to_cost_score"'));
  assert.ok(source.includes('format: "score"'));
});

test("Performance vs Cost chart wires its series labels from the shared variant map and drops High-End / Cost", () => {
  const source = fs.readFileSync(historyChartPath, "utf8");

  // Labels now come from getPerformanceSeriesLabels(variant); the chart no
  // longer hard-codes the simplified strings inline.
  assert.ok(source.includes("getPerformanceSeriesLabels"));
  assert.ok(source.includes("const seriesLabels = getPerformanceSeriesLabels(variant)"));
  assert.ok(source.includes("label={seriesLabels.mean}"));
  assert.ok(source.includes("label={seriesLabels.median}"));
  assert.ok(source.includes("label={seriesLabels.p95}"));
  assert.ok(source.includes("name={seriesLabels.mean}"));
  assert.ok(source.includes("name={seriesLabels.median}"));
  assert.ok(source.includes("name={seriesLabels.p95}"));
  // The tooltip must render in the same variant as the plotted lines.
  assert.ok(source.includes("variant={variant}"));
  assert.ok(!source.includes('label="God Pull Upside"'));
  assert.ok(!source.includes('name="God Pull Upside"'));
  assert.ok(!source.includes("High-End / Cost"));
  assert.ok(!source.includes("Mean / Cost"));
  assert.ok(!source.includes("Median / Cost"));
});

test("Performance series labels expose a market quick-read variant and a technical simulation variant", () => {
  const source = fs.readFileSync(performanceFormattingPath, "utf8");

  // Overview quick-read (market) keeps the simplified reader labels; the p95
  // upside is now "Realistic Upside" (renamed from "Big Hit Upside").
  assert.ok(source.includes('mean: "Expected Value"'));
  assert.ok(source.includes('median: "Typical Return"'));
  assert.ok(source.includes('p95: "Realistic Upside"'));
  assert.ok(!source.includes('"Big Hit Upside"'), "the confusing Big Hit Upside label must be gone");
  // Simulation Results (Opening Profit vs Cost) keeps the raw percentile-vs-cost labels.
  assert.ok(source.includes('mean: "Expected Value vs Cost"'));
  assert.ok(source.includes('median: "50th Percentile vs Cost"'));
  assert.ok(source.includes('p95: "95th Percentile vs Cost"'));
  assert.ok(source.includes("export const PERFORMANCE_SERIES_LABELS"));
  assert.ok(source.includes("export function getPerformanceSeriesLabels"));
  assert.ok(source.includes("buildPerformanceTooltipRows(row = {}, packCost = null, variant = \"market\")"));
});

test("Simulation Results card renames Opening Outcomes and lists all six sub-tabs", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes('title="Simulation Results"'));
  assert.ok(!source.includes('title="Opening Outcomes"'), "the set-detail card title must be reframed as Simulation Results");

  for (const label of [
    'label: "Outcome Distribution"',
    'label: "Opening Profit vs Cost"',
    'label: "Simulation Drivers"',
    'label: "Value Structure"',
    'label: "Pack Paths"',
    'label: "Metrics"',
  ]) {
    assert.ok(source.includes(label), `Simulation Results tabs must include ${label}`);
  }
  // The abbreviated "Opening P vs C" user-facing label must be gone.
  assert.ok(!source.includes('label: "Opening P vs C"'));

  // Opening Profit vs Cost reuses PackValueHistoryChart in the technical variant.
  assert.ok(source.includes('variant="simulation"'));
  // Metrics tab renders the dedicated grouped panel.
  assert.ok(source.includes("<SimulationMetricsContent"));
});

test("Simulation Results card drops the changing subtitle, keeps a stable info bubble, and gives every sub-tab a section header", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  // The card keeps ONE stable info bubble (not the old per-tab titleInfoText ternary).
  assert.ok(source.includes("titleInfoText={SIMULATION_RESULTS_INFO_TEXT}"));
  assert.ok(source.includes("const SIMULATION_RESULTS_INFO_TEXT ="));

  // The changing sub-tab subtitles are gone.
  assert.ok(!source.includes("Simulated opening performance vs pack cost over time"));
  assert.ok(!source.includes("percentile-vs-cost ratios kept technical"));
  // The Simulation Results SectionCard must not pass a subtitle prop anymore.
  const cardStart = source.indexOf('title="Simulation Results"', source.indexOf("<SectionCard"));
  const cardTabs = source.indexOf("<SectionViewTabs", cardStart);
  assert.ok(cardStart >= 0 && cardTabs > cardStart);
  assert.ok(!source.slice(cardStart, cardTabs).includes("subtitle="), "Simulation Results card must not render a subtitle");

  // Per-tab section header (title + info bubble).
  assert.ok(source.includes("function SimulationSectionHeader"));
  assert.ok(source.includes("<SimulationSectionHeader"));
  assert.ok(source.includes("const OPENING_PROFIT_VS_COST_INFO_TEXT ="));
  assert.ok(source.includes("const SIMULATION_METRICS_INFO_TEXT ="));
  // The Outcome Distribution child chart's duplicate internal title is suppressed.
  assert.ok(source.includes("showTitle={false}"));
});

test("Metrics tab drops Model Version and every metric row carries an info bubble", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  // Model/version fields are diagnostics-only, not user-facing here.
  assert.ok(!source.includes('label="Model Version"'));
  assert.ok(!source.includes("const modelVersion ="));

  // Every metric row goes through SimMetricLine, which auto-attaches an info
  // bubble from SIMULATION_METRIC_INFO — so no bare <SimMetricRow in the panel.
  assert.ok(source.includes("const SIMULATION_METRIC_INFO = {"));
  assert.ok(source.includes("function SimMetricLine("));
  assert.ok(source.includes("infoText={infoText ?? SIMULATION_METRIC_INFO[label] ?? null}"));

  const panelStart = source.indexOf("function SimulationMetricsContent");
  const panelEnd = source.indexOf("function formatDriverScore", panelStart);
  const panelSource = source.slice(panelStart, panelEnd);
  assert.ok(panelStart >= 0 && panelEnd > panelStart);
  assert.ok(!panelSource.includes("<SimMetricRow"), "the panel must render rows via SimMetricLine so every row is explained");
  // Honest unavailable state for calculated-vs-simulated agreement is preserved.
  assert.ok(panelSource.includes("Calculated-vs-simulated agreement is not available in this snapshot yet."));

  // Metrics must NOT gain a category/sub selector, and must keep its own scroll.
  assert.ok(!panelSource.includes("SectionViewTabs"), "Metrics must not add a category selector");
  assert.ok(!panelSource.includes("SegmentedControl"), "Metrics must not add a category selector");
});

test("RipDistributionChart supports a flush (no inner card) mode, defaulting to the bordered card", () => {
  const chartSource = fs.readFileSync(historyChartPath, "utf8"); // sanity: shared import path resolves
  assert.ok(chartSource.length > 0);

  const dist = fs.readFileSync(distributionChartPath, "utf8").replace(/\r\n/g, "\n");
  // Opt-in prop; default preserves the bordered standalone-card look elsewhere.
  assert.ok(dist.includes("flush = false"));
  // The flush branch drops the rounded border/background/standalone padding.
  assert.ok(dist.includes('flush\n          ? "w-full max-w-full min-w-0"'));
  assert.ok(dist.includes('rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 p-3 sm:p-4 md:p-5'));
});

test("Simulation Results non-Metrics sub-tabs render flush (no internal scroll); Metrics keeps its scroll", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  // A shared flush body wrapper exists and is used by the non-Metrics tabs.
  assert.ok(source.includes("function SimulationResultsPanel("));
  assert.ok(source.includes('<SimulationResultsPanel id="set-detail-outcome-distribution">'));
  assert.ok(source.includes('<SimulationResultsPanel id="set-detail-simulation-drivers">'));
  assert.ok(source.includes('<SimulationResultsPanel id="set-detail-value-structure">'));
  assert.ok(source.includes('<SimulationResultsPanel id="set-detail-pack-breakdown">'));
  assert.ok(source.includes('<SimulationResultsPanel id="set-detail-opening-performance-cost">'));

  // The wrapper carries no scroll/border/panel chrome.
  const panelStart = source.indexOf("function SimulationResultsPanel(");
  const panelEnd = source.indexOf("\n}", panelStart);
  const panelSource = source.slice(panelStart, panelEnd);
  assert.ok(!panelSource.includes("overflow-y-auto"));
  assert.ok(!panelSource.includes("max-h-"));
  assert.ok(!panelSource.includes("border"));

  // The five non-Metrics sub-tab branches no longer wrap content in an
  // overflow-y-auto / max-h scroll box.
  for (const id of [
    "set-detail-simulation-drivers",
    "set-detail-value-structure",
    "set-detail-pack-breakdown",
  ]) {
    assert.ok(
      !source.includes(`<div id="${id}" className="max-h-[32rem] scroll-mt-24 overflow-y-auto pr-1`),
      `${id} must no longer use an internal scroll wrapper`
    );
  }

  // Metrics is deliberately still allowed to scroll (not forced into the panel).
  assert.ok(source.includes('<div id="set-detail-simulation-metrics" className="max-h-[36rem] scroll-mt-24 overflow-y-auto pr-1 md:scroll-mt-28">'));
});

test("Outcome Distribution renders flush inside Simulation Results, matching Opening Profit vs Cost", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");
  assert.ok(source.includes("<RipDistributionChart bins={distributionBins} thresholdBins={thresholdBins} markers={chartMarkers} showTitle={false} flush />"));
});

test("Simulation Drivers caps rows, while Value Structure uses a ribbon and all-groups grid in Simulation Results", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  // Compact image container + compact/maxRows props are opt-in and wired only
  // for the Simulation Results driver usage.
  assert.ok(source.includes("const TOP_CARD_IMAGE_CONTAINER_COMPACT_CLASS ="));
  assert.ok(source.includes("compactImage ? TOP_CARD_IMAGE_CONTAINER_COMPACT_CLASS : TOP_CARD_IMAGE_CONTAINER_CLASS"));
  assert.ok(source.includes("<TopEVDriversContent topHits={topHits} meanValue={summary.mean_value} condensed compactImage maxRows={8}"));
  assert.ok(source.includes("Showing top {hits.length} EV drivers"));

  assert.ok(source.includes("function RarityValueComposition("));
  assert.ok(source.includes("function ValueCompositionRibbon("));
  assert.ok(source.includes("function RarityDetailTile("));
  assert.ok(source.includes("<RarityContributionContent rankings={rankings} condensed />"));
  assert.ok(source.includes("<ValueCompositionRibbon rows={rows} totalValue={totalValue} totalPulls={totalPulls} />"));
  assert.ok(source.includes("buildRarityCompositionRows(rankings)"));
  assert.ok(source.includes("SIMULATION_COMPOSITION_COLORS"));
  assert.ok(!source.includes("<Treemap"));
  assert.ok(!source.includes("SIMULATION_TREEMAP_COLORS"));
  assert.ok(!source.includes("rgba(168,85,247"));
  assert.ok(!source.includes("rgba(251,191,36,0.72"));
  assert.ok(!source.includes("+{hiddenRarityCount} more rarity groups"));
  assert.ok(!source.includes("condensed maxRows={8}"));
});

test("Pack Paths uses a restrained donut plus all-states matrix in Simulation Results", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  assert.ok(source.includes('import { aggregateNormalStateRows } from "./packStateLabels.mjs";'));
  assert.ok(source.includes("function PackPathsVisualization("));
  assert.ok(source.includes("buildTopLevelPackPathRows(packPaths)"));
  assert.ok(source.includes("buildNormalStateMatrixRows(normalStateRows)"));
  assert.ok(source.includes("function NormalStateMatrix("));
  assert.ok(source.includes("function StateMatrixTile("));
  assert.ok(source.includes("Normal State Matrix"));
  assert.ok(source.includes("<PieChart>"));
  assert.ok(source.includes("<Pie"));
  assert.ok(!source.includes("<Treemap"));
  assert.ok(!source.includes("buildNormalStateTreemapRows"));
  assert.ok(source.includes("aggregateNormalStateRows(Array.isArray(stateRows) ? stateRows : [])"));
  assert.ok(!source.includes("+{hiddenCount} more states"));
  assert.ok(!source.includes("collapseDuplicates={condensed}"));
  assert.ok(!source.includes("maxRows={condensed ? 8 : null}"));
});

test("Performance vs Cost info bubble explains chart series and P95 basis", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes("<p>Tracks how simulated opening outcomes compare against pack market price over time.</p>"));
  assert.ok(source.includes("<span className=\"font-semibold text-[var(--text-primary)]\">Expected Value:</span> average simulated pack value."));
  assert.ok(source.includes("<span className=\"font-semibold text-[var(--text-primary)]\">Typical Return:</span> median simulated pack value."));
  assert.ok(source.includes("<span className=\"font-semibold text-[var(--text-primary)]\">Realistic Upside:</span> 95th percentile simulated pack outcome. Roughly 5% of simulated packs landed above this value."));
  assert.ok(source.includes("Above 1.0x means that outcome is above pack market price; below 1.0x means it is below pack market price."));
  assert.ok(
    source.indexOf("Realistic Upside:</span> 95th percentile simulated pack outcome") <
      source.indexOf("Expected Value:</span> average simulated pack value.")
  );
  assert.ok(
    source.indexOf("Expected Value:</span> average simulated pack value.") <
      source.indexOf("Typical Return:</span> median simulated pack value.")
  );
  assert.ok(source.includes("titleInfoText={PERFORMANCE_VS_COST_INFO_TEXT}"));
  assert.ok(source.includes("? PERFORMANCE_VS_COST_INFO_TEXT"));
});

test("Performance vs Cost metrics include God Pull Upside tile wired to P99 ratio", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes('godPullUpside: "God Pull Upside"'));
  assert.ok(source.includes('label={RIP_COPY.chartStats.godPullUpside}'));
  assert.ok(source.includes('value={formatMultiplier(summary.p99_value_to_cost_ratio, 1)}'));
  assert.ok(source.includes("Simple: Rare monster-hit outcome compared with pack price."));
  assert.ok(source.includes("Expert: P99 outcome vs pack cost."));
});

test("Explore Biggest Upside mode uses blended biggest_upside ranking fields", () => {
  const source = fs.readFileSync(rankingConfigPath, "utf8");

  assert.ok(source.includes('scoreField: "relative_biggest_upside_score"'));
  assert.ok(source.includes('rankField: "biggest_upside_rank"'));
  assert.ok(source.includes('tierField: "biggest_upside_tier"'));
  assert.ok(!source.includes('scoreField: "p95_value_to_cost_ratio"'));
});

test("Explore God Pull Upside mode uses P99 ratio display with P99 ranking fields", () => {
  const source = fs.readFileSync(rankingConfigPath, "utf8");

  assert.ok(source.includes('id: "godPullUpside"'));
  assert.ok(source.includes('label: "God Pull Upside"'));
  assert.ok(source.includes('scoreField: "p99_value_to_cost_ratio"'));
  assert.ok(source.includes('scoreFormat: "ratio"'));
  assert.ok(source.includes('rankField: "p99_value_to_cost_rank"'));
  assert.ok(source.includes('tierField: "p99_value_to_cost_tier"'));
});

test("Desirability pillar uses updated public labels and breakdown rows", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes('title="Desirability"'));
  assert.ok(!source.includes('title="Opening Desirability"'));
  assert.ok(!source.includes('label: "How It Works"'));
  assert.ok(!source.includes('label: "Opening Desirability"'));
  assert.ok(source.includes('label: "Collector Appeal"'));
  assert.ok(source.includes('label: "Chase Appeal"'));
  assert.ok(!source.includes('label: "Source"'));
  assert.ok(!source.includes('value: "Opening Desirability model"'));
  assert.ok(source.includes("SIMPLE_PILLAR_INFO_COPY.Desirability"));
  assert.ok(source.includes("headline score is adjusted for set-to-set ranking"));
  assert.ok(source.includes('"Needs chase data"'));
  assert.ok(source.includes("topCollectorAppealDrivers"));
  assert.ok(source.includes("openingPayload?.topCollectorAppealDrivers"));
  assert.ok(source.includes("explorePayload?.openingDesirability?.topCollectorAppealDrivers"));
  assert.ok(source.includes("function CollectorAppealDriverRow"));
  assert.ok(source.includes("<CollectorAppealDriverRow"));
  assert.ok(source.includes("Pokémon Appeal:"));
  assert.ok(!source.includes("Card Appeal:"));
  assert.ok(!source.includes("Why it matters:"));
  assert.ok(!source.includes('<OpeningDesirabilityCard'));
});

test("Top Collector Appeal Drivers empty state copy is specific to missing set data", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes("Top Collector Appeal drivers are not available for this set yet."));
});
