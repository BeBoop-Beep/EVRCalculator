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

  // The card renders its own collapsible header (h2), no longer a SectionCard title prop.
  assert.ok(source.includes(">Simulation Results</h2>"));
  assert.ok(!source.includes('title="Opening Outcomes"'), "the set-detail card title must be reframed as Simulation Results");

  for (const label of [
    'label: "Outcome Distribution"',
    'label: "Opening Performance vs Cost"',
    'label: "Simulation Drivers"',
    'label: "Value Structure"',
    'label: "Pack Paths"',
    'label: "Metrics"',
  ]) {
    assert.ok(source.includes(label), `Simulation Results tabs must include ${label}`);
  }
  // The abbreviated "Opening P vs C" user-facing label must be gone, and the
  // pre-rename "Opening Profit vs Cost" label must not resurface (unified as
  // "Opening Performance vs Cost" across Overview + Insights).
  assert.ok(!source.includes('label: "Opening P vs C"'));
  assert.ok(!source.includes("Opening Profit vs Cost</"), "no rendered text may still say Opening Profit vs Cost");

  // Opening Profit vs Cost reuses PackValueHistoryChart in the technical variant.
  assert.ok(source.includes('variant="simulation"'));
  // Metrics tab renders the dedicated grouped panel.
  assert.ok(source.includes("<SimulationMetricsContent"));
});

test("Simulation Results card drops the changing subtitle, keeps a stable info bubble, and gives every sub-tab a section header", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  // The card keeps ONE stable info bubble (not the old per-tab titleInfoText
  // ternary) — now rendered directly in the collapsible header row.
  assert.ok(source.includes("<InfoPopover text={SIMULATION_RESULTS_INFO_TEXT} />"));
  assert.ok(source.includes("const SIMULATION_RESULTS_INFO_TEXT ="));

  // The changing sub-tab subtitles are gone; the header carries one static kicker.
  assert.ok(!source.includes("Simulated opening performance vs pack cost over time"));
  assert.ok(!source.includes("percentile-vs-cost ratios kept technical"));
  const cardStart = source.indexOf(">Simulation Results</h2>");
  const cardTabs = source.indexOf("<SectionViewTabs", cardStart);
  assert.ok(cardStart >= 0 && cardTabs > cardStart);
  assert.ok(!source.slice(cardStart, cardTabs).includes("subtitle="), "Simulation Results card must not render a per-tab subtitle");
  assert.ok(
    source.slice(cardStart, cardTabs).includes("The raw evidence — full simulation outputs behind the score."),
    "Simulation Results header must carry its static kicker"
  );

  // Per-tab section header (title + info bubble).
  assert.ok(source.includes("function SimulationSectionHeader"));
  assert.ok(source.includes("<SimulationSectionHeader"));
  assert.ok(source.includes("const OPENING_PERFORMANCE_VS_COST_INFO_TEXT ="));
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

test("Metrics tab three-tier redesign: verdict row removed, log-scale percentile strip leads, question-grouped disclosures", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");
  const panelStart = source.indexOf("function SimulationMetricsContent");
  const panelEnd = source.indexOf("function formatDriverScore", panelStart);
  const panelSource = source.slice(panelStart, panelEnd);

  // The former Tier-1 verdict cards (Expected Value / EV/Cost / Typical Pack /
  // Chance to Profit) are gone — that data leads the Overview hero and the RIP
  // Score Breakdown, and each figure stays reachable in the grouped rows.
  assert.ok(!source.includes("function VerdictStatCard("), "the verdict stat card component must be removed with its row");
  assert.ok(!panelSource.includes("<VerdictStatCard"), "the Metrics panel must not render verdict stat cards");
  assert.ok(
    panelSource.includes('label="EV / Cost"') && panelSource.includes('label="Chance to Beat Pack Cost"'),
    "the removed verdict figures must stay reachable in the grouped rows"
  );
  // The percentile strip is now the first content element after the tab's description line.
  const descriptionIndex = panelSource.indexOf("Raw simulation outputs and the metrics derived from them.");
  const stripIndex = panelSource.indexOf("Where Packs Land");
  const disclosureIndex = panelSource.indexOf("<SimMetricDisclosureCard");
  assert.ok(
    descriptionIndex >= 0 && stripIndex > descriptionIndex && disclosureIndex > stripIndex,
    "Metrics must read description → percentile strip → question cards"
  );

  // Tier 2: hand-rolled SVG strip on a log scale, replacing the percentile table.
  assert.ok(source.includes("function PercentileStripChart("), "the percentile strip component must exist");
  assert.ok(panelSource.includes("buildPercentileStripModel"), "the strip model is computed from live values");
  assert.ok(panelSource.includes("buildPercentileTakeaway"), "the strip takeaway is computed, not hardcoded");
  assert.ok(panelSource.includes("log scale"), "the log scale is noted in the card header area");
  const stripStart = source.indexOf("function PercentileStripChart(");
  const stripEnd = source.indexOf("function SimMetricDisclosureCard(", stripStart);
  const stripSource = source.slice(stripStart, stripEnd);
  assert.ok(stripStart >= 0 && stripEnd > stripStart);
  assert.ok(stripSource.includes('role="img"'), "the strip SVG is labeled as an image");
  assert.ok(stripSource.includes("aria-label={ariaLabel}"), "the strip carries a descriptive aria-label from live values");
  assert.ok(stripSource.includes('className="sr-only"'), "a visually-hidden percentile list backs the strip");
  assert.ok(stripSource.includes("Pack cost"), "the dashed pack-cost line is labeled");
  assert.ok(stripSource.includes('strokeDasharray="4 4"'), "the pack-cost anchor line is dashed");
  assert.ok(!stripSource.includes('from "recharts"'), "the strip is hand-rolled SVG, not a chart-library chart");

  // Tier 3: four plain-language question cards, first one expanded.
  assert.ok(panelSource.includes('question="Will I lose money?" defaultOpen'), "the first disclosure starts expanded");
  for (const question of ["What's the upside?", "How swingy is it?", "How was this simulated?"]) {
    assert.ok(panelSource.includes(`question="${question}"`), `disclosure grid must include ${question}`);
  }
  assert.ok(source.includes("<details"), "disclosures use the native details/summary pattern");
  assert.ok(panelSource.includes("tag={coefficientOfVariationTag}"), "CV row carries its judgment tag");
  assert.ok(panelSource.includes("tag={hhiConcentrationTag}"), "HHI row carries its judgment tag");

  // Removals: Variance display gone (kept in the data layer), Std Dev shown once,
  // loss fractions merge when equal after rounding.
  assert.ok(!panelSource.includes('label="Variance"'), "Variance must be removed from the display");
  assert.equal(panelSource.split('label="Std Dev"').length - 1, 1, "Std Dev must display exactly once");
  assert.ok(panelSource.includes("lossFractionMerged"), "equal loss fractions collapse to a single row");
  assert.ok(panelSource.includes('label="Loss Fraction"'), "the merged Loss Fraction row exists");

  // Shared formatter: the tab's value helpers all route through the
  // simulationMetricsDisplay formatters.
  for (const formatter of ["formatMetricCurrency", "formatMetricRatio", "formatMetricProbability", "formatMetricPercent", "formatMetricCount"]) {
    assert.ok(panelSource.includes(formatter), `Metrics values must pass through ${formatter}`);
  }
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

test("Simulation Drivers renders a compact ranked list, while Value Structure uses truthful contribution rails for all rarity groups", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  // Simulation Results drivers keep the title row tight, align the EV summary
  // with the interpretation callout, show all ten compact ranked rows, and
  // suppress the old "top 8 + more" footer.
  assert.ok(source.includes("const TOP_CARD_IMAGE_CONTAINER_COMPACT_CLASS ="));
  assert.ok(source.includes("function TopDriverListRow("));
  assert.ok(source.includes("rank={columnIndex * 5 + index + 1}"));
  assert.ok(source.includes("hits.slice(0, 5)"));
  assert.ok(source.includes("hits.slice(5)"));
  assert.ok(source.includes('className={activeInsightsGraphMode === "simulation-drivers" ? "mb-1.5" : "mb-3"}'));
  assert.ok(source.includes('lg:grid-cols-[minmax(0,1fr)_auto]'));
  assert.ok(!source.includes("rightContent={"));
  assert.ok(source.includes("Simulated Expected Value"));
  assert.ok(source.includes("simulationDriversSummaryValue"));
  assert.ok(source.includes("maxRows={10}"));
  assert.ok(source.includes("showSummary={false}"));
  assert.ok(source.includes("showHiddenCountFooter={false}"));

  assert.ok(source.includes("function RarityContributionRails("));
  assert.ok(source.includes("function ContributionBarList("));
  assert.ok(source.includes('import CompactRankedBarChart from "@/components/explore/CompactRankedBarChart";'));
  assert.ok(
    !source.includes("function ContributionBarRow("),
    "the per-row HTML progress-bar rows are replaced by the shared compact chart"
  );
  assert.ok(source.includes("<RarityContributionContent rankings={rankings} condensed />"));
  assert.ok(source.includes("buildRarityCompositionRows(rankings)"));
  const rarityRowsStart = source.indexOf("function buildRarityCompositionRows(rankings)");
  const rarityRowsEnd = source.indexOf("function SimulationChartTooltipFrame", rarityRowsStart);
  const rarityRowsSource = source.slice(rarityRowsStart, rarityRowsEnd);
  assert.ok(!rarityRowsSource.includes(".filter("), "Value Structure must retain all rarity groups for the chart");
  assert.ok(source.includes("sharePercent: totalValue > 0 ? (row.value / totalValue) * 100 : 0,"), "Value Structure bars use real value share");
  // Value Structure is now ONE unified contribution panel (header + ranked
  // single-column bars), not a multi-column grid of disconnected rails.
  assert.ok(source.includes('title="Total Simulated Value"'), "the total lives in the unified panel header");
  assert.ok(source.includes("headerValue={formatCurrency(totalValue)}"));
  assert.ok(!source.includes("grid-cols-1 gap-x-5"), "the old multi-column rail grid must be gone");
  assert.ok(!source.includes("md:grid-cols-2 xl:grid-cols-3"), "contribution rails must no longer be a responsive grid");
  assert.ok(!source.includes("function ContributionRail("), "ContributionRail is renamed to ContributionBarRow");
  assert.ok(!source.includes("function RarityValueComposition("));
  assert.ok(!source.includes("function SiteNativeTreemapTile("));
  assert.ok(!source.includes("function ValueStructureTreemapTooltip("));
  assert.ok(!source.includes("function ValueCompositionRibbon("));
  assert.ok(!source.includes("function RarityDetailTile("));
  assert.ok(!source.includes("<ValueCompositionRibbon"));
  assert.ok(!source.includes("function ValueLadderTile("));
  assert.ok(!source.includes("Value Ladder"));
  assert.ok(!source.includes("<Treemap"));
  assert.ok(!source.includes("SIMULATION_TREEMAP_COLORS"));
  assert.ok(!source.includes("LARGE_TILE_THRESHOLD"));
  assert.ok(!source.includes("MEDIUM_TILE_THRESHOLD"));
  assert.ok(!source.includes("rgba(168,85,247"));
  assert.ok(!source.includes("rgba(251,191,36,0.72"));
  assert.ok(!source.includes("+{hiddenRarityCount} more rarity groups"));
  assert.ok(!source.includes("condensed maxRows={8}"));
});

test("Pack Paths uses a compact donut plus an all-state contribution rail matrix", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  assert.ok(source.includes('import { aggregateNormalStateRows } from "./packStateLabels.mjs";'));
  assert.ok(source.includes("function PackPathsVisualization("));
  assert.ok(source.includes("buildTopLevelPackPathRows(packPaths)"));
  assert.ok(source.includes("buildNormalStateContributionRows(normalStateRows)"));
  assert.ok(source.includes("function PackPathDonutTooltip("));
  assert.ok(source.includes("function NormalStateContributionRails("));
  assert.ok(source.includes("Normal State Distribution"));
  assert.ok(source.includes("<PieChart"));
  assert.ok(source.includes("<Pie"));
  assert.ok(source.includes("PACK_PATH_CHART_COLORS"));
  assert.ok(source.includes("sharePercent: totalStates > 0 ? (row.count / totalStates) * 100 : 0,"), "state bars use real count share");
  // Normal State Distribution renders through the SAME unified contribution
  // panel as Value Structure, with its title as the internal header row, and
  // the SAME shared compact ranked bar chart inside it.
  assert.ok(source.includes('<ContributionBarList title="Normal State Distribution">'), "Normal State Distribution reuses the unified panel");
  assert.ok(source.includes("<NormalStateChartTooltip />"), "state chart tooltip carries the full underlying data");
  assert.ok(source.includes('allowEscapeViewBox={{ x: true, y: true }}'));
  assert.ok(source.includes('wrapperStyle={{ zIndex: 9999, pointerEvents: "none" }}'));
  assert.ok(source.includes('ChartFrame className="h-full w-full overflow-visible"'));
  assert.ok(!source.includes("function NormalStateTreemap("));
  assert.ok(!source.includes("function NormalStateTreemapTooltip("));
  assert.ok(!source.includes("buildNormalStateMatrixRows"));
  assert.ok(!source.includes("buildNormalStateTreemapRows"));
  assert.ok(!source.includes("function PathMixSummary("));
  assert.ok(!source.includes("function PathMixRow("));
  assert.ok(!source.includes("function NormalStateMatrix("));
  assert.ok(!source.includes("function StateMatrixTile("));
  assert.ok(source.includes("aggregateNormalStateRows(Array.isArray(stateRows) ? stateRows : [])"));
  const stateRowsStart = source.indexOf("function buildNormalStateContributionRows(stateRows)");
  const stateRowsEnd = source.indexOf("function buildRarityCompositionRows", stateRowsStart);
  assert.ok(!source.slice(stateRowsStart, stateRowsEnd).includes(".filter("), "Pack Paths must retain every normalized state row");
  assert.ok(!source.includes("+{hiddenCount} more states"));
  assert.ok(!source.includes("collapseDuplicates={condensed}"));
  assert.ok(!source.includes("maxRows={condensed ? 8 : null}"));
});

test("Pack Paths donut renders every nonzero path as a real in-ring slice with an amber God Pack sliver", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  // Single shared adaptive formatter module wired into the page.
  assert.ok(source.includes('from "./packPathShare.mjs"'));
  assert.ok(source.includes("formatShareFromCounts"));
  assert.ok(source.includes("formatImpliedOdds"));

  // God Pack uses the restrained amber/gold semantic accent (not the old muted
  // slate-teal that was indistinguishable from Normal), applied to its Cell.
  assert.ok(source.includes('god_pack: "rgba(245,182,74,0.92)"'));
  assert.ok(!source.includes('god_pack: "rgba(71,118,132,0.72)"'), "the old indistinguishable God Pack color must be gone");
  assert.ok(source.includes("{displayPathRows.map((row) => <Cell key={`path-slice:${row.key}`} fill={row.fill} />)}"));

  // Every pack-path share renderer (center, legend, tooltip, chips) goes through
  // the adaptive formatter instead of the fixed 1-decimal formatShare, so a
  // nonzero rare path can never render "0.0%".
  assert.ok(source.includes("{dominantPath.name} {formatShareFromCounts(dominantPath.count, totalPacks)}"));
  assert.ok(source.includes("formatShareFromCounts(row.count, totalPacks)"));
  assert.ok(source.includes("getPackPathEvidenceRowsFromCounts(ripStatistics?.pack_paths)"));

  // The tiny nonzero God Pack path is drawn with DISPLAY-ONLY rescaled slice
  // weights so its sector is recognizable (~7%); real counts/shares stay in text.
  assert.ok(source.includes("buildPackPathDisplayRows"));
  assert.ok(source.includes("const displayPathRows = buildPackPathDisplayRows(visiblePathRows);"));
  assert.ok(source.includes("data={displayPathRows}"));
  assert.ok(source.includes('dataKey="displayWeight"'));
  assert.ok(source.includes("paddingAngle={0}"));
  assert.ok(source.includes("cornerRadius={0}"));
  assert.ok(source.includes('stroke="none"'));

  // The donut is physically larger (~1.5x) so the rescaled slices read clearly.
  assert.ok(source.includes("h-[13.125rem]"));
  assert.ok(source.includes("sm:h-[14.25rem]"));
  assert.ok(!source.includes("h-[8.75rem]"), "the old smaller donut height must be gone");
  assert.ok(!source.includes("sm:h-[9.5rem]"), "the old smaller donut height must be gone");

  // The visual minimum-angle floor and the external outer-ring marker are both
  // gone — the display-weight rescale is the single visibility mechanism.
  assert.ok(!source.includes("minAngle={1.25}"), "the minAngle floor is replaced by display-weight rescaling");
  assert.ok(!source.includes("path-marker:"), "the external rare-path marker must be gone");
  assert.ok(!source.includes("hasRareMarker"), "the rare-path marker gate must be gone");
  assert.ok(!source.includes("rareMarkerKeys"), "the rare-path marker key set must be gone");
  assert.ok(!source.includes('outerRadius="92%"'), "the external outer marker ring must be gone");
  assert.ok(!source.includes("minAngle={4}"), "the external marker's min angle must be gone");

  // The donut still only renders wedges for nonzero paths (via visiblePathRows).
  assert.ok(source.includes("const visiblePathRows = pathRows.filter((row) => row.count > 0);"));

  // Tooltip surfaces implied odds only when they are meaningful.
  assert.ok(source.includes("const impliedOdds = formatImpliedOdds(row.count, totalPacks);"));
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

test("Simulation context boxes share one surface primitive and drop the older one-off surfaces", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  // A single shared Simulation context-surface primitive + class constant exists,
  // so future depth/tone tweaks stay synchronized across the whole family.
  assert.ok(source.includes("const SIMULATION_CONTEXT_SURFACE_CLASS ="));
  assert.ok(source.includes("function SimulationContextSurface("));
  assert.ok(source.includes("`${SIMULATION_CONTEXT_SURFACE_CLASS} ${className}`"));

  // Total Simulated Value now renders through the shared surface and no longer
  // carries its bespoke /55 wrapper (scoped to RarityContributionContent so the
  // evidence-chip /55 elsewhere is not implicated).
  const rccStart = source.indexOf("function RarityContributionContent(");
  const rccEnd = source.indexOf("function PackPathBars(", rccStart);
  const rccSource = source.slice(rccStart, rccEnd);
  assert.ok(rccStart >= 0 && rccEnd > rccStart);
  assert.ok(rccSource.includes("Total Simulated Value"));
  assert.ok(rccSource.includes("<SimulationContextSurface as=\"div\""), "Total Simulated Value must render inside the shared surface");
  assert.ok(!rccSource.includes("bg-[var(--surface-page)]/55"), "Total Simulated Value must drop its one-off /55 surface");

  // The Metrics tab's cards all render on the shared surface class: disclosure
  // cards compose SIMULATION_CONTEXT_SURFACE_CLASS directly (details elements
  // can't wrap the component), and the percentile strip card uses the
  // component. The old flat SimMetricGroup wrapper is gone with the flat table
  // layout, and the Tier-1 verdict cards were removed outright (their data
  // lives in the Overview hero / RIP Score Breakdown / grouped rows).
  assert.ok(!source.includes("function SimMetricGroup("), "the old flat metric group wrapper is replaced by the tiered Metrics cards");
  assert.ok(!source.includes("function VerdictStatCard("), "the verdict stat cards were removed with the Metrics hero row");
  const disclosureStart = source.indexOf("function SimMetricDisclosureCard(");
  const disclosureEnd = source.indexOf("\n}", disclosureStart);
  assert.ok(disclosureStart >= 0 && disclosureEnd > disclosureStart, "SimMetricDisclosureCard must exist");
  assert.ok(
    source.slice(disclosureStart, disclosureEnd).includes("SIMULATION_CONTEXT_SURFACE_CLASS"),
    "disclosure cards must render on the shared context surface class"
  );

  // Behavioral contracts are untouched by the visual pass: metric rows still flow
  // through SimMetricLine, the Metrics scroll wrapper stays, info bubbles remain,
  // and Model Version stays absent.
  assert.ok(source.includes("function SimMetricLine("));
  assert.ok(source.includes("infoText={infoText ?? SIMULATION_METRIC_INFO[label] ?? null}"));
  assert.ok(source.includes('<div id="set-detail-simulation-metrics" className="max-h-[36rem] scroll-mt-24 overflow-y-auto pr-1 md:scroll-mt-28">'));
  assert.ok(!source.includes('label="Model Version"'));
});

test("Simulation Results unifies Value Structure and Normal State Distribution into one compact ranked bar chart language", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  // ONE shared static Recharts chart backs BOTH distributions.
  assert.ok(source.includes('import CompactRankedBarChart from "@/components/explore/CompactRankedBarChart";'), "the shared compact chart must be imported");
  assert.ok(source.includes("function ContributionBarList("), "reusable flush chart section primitive must exist");
  const chartUsageCount = source.split("<CompactRankedBarChart").length - 1;
  assert.ok(chartUsageCount >= 2, "Value Structure AND Normal State Distribution must both render the shared chart");

  // The shared chart section is flush inside Simulation Results: an internal
  // header row, a divider, then the chart — not a nested context card, not a
  // top box floating above a second box, and never one card per row.
  const listStart = source.indexOf("function ContributionBarList(");
  const listEnd = source.indexOf("\n}", listStart);
  const listSource = source.slice(listStart, listEnd);
  assert.ok(listStart >= 0 && listEnd > listStart);
  assert.ok(listSource.includes('<div className="min-w-0 overflow-visible">'), "the shared section must be flush, not a context surface");
  assert.ok(!listSource.includes("<SimulationContextSurface"), "the shared section must not add an inner context-card shell");
  assert.ok(listSource.includes("border-t border-white/10"), "header and chart are separated by the thin divider");
  assert.ok(listSource.includes("overflow-visible"), "the section body must not clip the chart tooltip");

  // Value Structure: the Total Simulated Value header + total live inside the
  // flush chart section (RarityContributionRails), and condensed mode returns
  // only that section (no stacked disconnected top/bottom boxes).
  assert.ok(source.includes('title="Total Simulated Value"'), "Value Structure total is the flush section header");
  assert.ok(source.includes("headerValue={formatCurrency(totalValue)}"), "the total renders on the panel header row");
  const rccStart = source.indexOf("function RarityContributionContent(");
  const rccEnd = source.indexOf("function PackPathBars(", rccStart);
  const rccSource = source.slice(rccStart, rccEnd);
  assert.ok(rccStart >= 0 && rccEnd > rccStart);
  assert.ok(rccSource.includes("if (condensed) {"), "condensed Value Structure must early-return the flush chart section");
  assert.ok(
    rccSource.includes("return <RarityContributionRails rankings={rankings} />;"),
    "condensed Value Structure renders one flush section, not a top box plus a rails box"
  );
  assert.ok(source.includes("sharePercent: totalValue > 0 ? (row.value / totalValue) * 100 : 0,"), "Value Structure bars use real value share");
  assert.ok(source.includes("formatAbbreviatedCurrency(row.value)"), "the right column shows the abbreviated simulated value");
  assert.ok(source.includes("<RarityContributionChartTooltip />"), "exact values, pull count, and pull share live in the tooltip");

  // Pack Paths keeps the donut with the same title + divider treatment and
  // renders Normal State Distribution through the shared chart section.
  assert.ok(source.includes("<PieChart"), "Pack Paths must keep the donut");
  assert.ok(source.includes('<p className="pb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Pack Paths</p>'), "Pack Paths title must sit directly above the divider");
  assert.ok(source.includes('<div className="min-w-0 overflow-visible border-t border-white/10 pt-1.5">'), "Pack Paths donut must use the same thin divider treatment");
  assert.ok(source.includes('<ContributionBarList title="Normal State Distribution">'), "Normal State Distribution reuses the shared chart section");
  assert.ok(source.includes("sharePercent: totalStates > 0 ? (row.count / totalStates) * 100 : 0,"), "state bars use real count share");
  assert.ok(source.includes("formatAbbreviatedCount(row.count)"), "the right column shows the abbreviated state count");
  assert.ok(source.includes("totalPacks={totalPacks}"), "the state tooltip can report share of all simulated packs");

  // Descending sort + all rows retained for both distributions.
  assert.ok(source.includes(".sort((left, right) => right.value - left.value)"), "rarity rows are sorted descending by value");
  const stateRowsStart = source.indexOf("function buildNormalStateContributionRows(stateRows)");
  const stateRowsEnd = source.indexOf("function buildRarityCompositionRows", stateRowsStart);
  assert.ok(!source.slice(stateRowsStart, stateRowsEnd).includes(".filter("), "every normalized state row is retained");

  // The oversized per-row UI is fully removed: no per-row progress bars, no
  // second metadata line under every bar, no hidden-row escape hatches, no
  // multi-column grid. Metrics behavior is untouched by this visual pass.
  assert.ok(!source.includes("function ContributionBarRow("), "the old per-row renderer must be removed, not left alongside the chart");
  assert.ok(!source.includes("secondaryValue={"), "no permanent second metadata line renders under chart rows");
  assert.ok(!source.includes("+{hiddenRarityCount} more rarity groups"));
  assert.ok(!source.includes("+{hiddenCount} more states"));
  assert.ok(!source.includes("md:grid-cols-2 xl:grid-cols-3"), "contribution charts are one ranked plot, not a responsive grid");
  assert.ok(!source.includes("grid-cols-1 gap-x-5"));
  assert.ok(!source.includes("function ContributionRail("), "the old rail primitive stays gone");
  assert.ok(source.includes("function SimMetricLine("));
  assert.ok(source.includes('<div id="set-detail-simulation-metrics" className="max-h-[36rem] scroll-mt-24 overflow-y-auto pr-1 md:scroll-mt-28">'));
});
