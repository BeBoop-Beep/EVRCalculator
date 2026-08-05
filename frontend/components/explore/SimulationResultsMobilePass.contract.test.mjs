// Simulation Results and Collector Profile below 1200px — the refinement pass
// that followed the shell cleanup.
//
// The shells were already flat; what remained were the contents. Six verbose
// sub-tab labels truncated into ellipses on a phone; the Outcome Distribution
// spent 32-44px of a 320px viewport on percentage tick labels and stacked six
// "Label: $0.00" chips under a chart that already plots those numbers; the
// Simulation Drivers gave each of ten cards a two-column block of labelled
// values; Metrics opened on five bordered surfaces and ~40 rows; and Collector
// Profile's three-stage summary spent most of a screen on three 28px scores.
//
// Every fix here is composition. The approved data removals are exactly four
// and each is asserted below to be a VISIBILITY change, with the underlying
// field still produced by its selector and still rendered at 1200px+:
//
//   1. the Collector Appeal weighted contribution row (asserted in
//      RipBreakdownMobileFeed.contract.test.mjs, which owns that section)
//   2. Outcome Distribution Y-axis tick labels
//   3. the persistent numeric value inside each distribution marker chip
//   4. Pack Paths' Dominant path / Dominant path share / Special path share
//
// RipStatisticsPageClient.jsx cannot be imported outside the Next build (it
// uses extensionless "@/..." specifiers only the bundler resolves), so the
// structural assertions read the rendered JSX source, matching every other
// contract test for this page. The file carries mixed CRLF/LF, so it is
// normalised before any multi-line anchor is searched for.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (relativePath) =>
  fs.readFileSync(path.join(here, relativePath), "utf8").replace(/\r\n/g, "\n");

const source = read("RipStatisticsPageClient.jsx");
const chart = read("RipDistributionChart.jsx");
const segmented = read("../ui/SegmentedControl.jsx");
const globals = read("../../app/styles/globals.css");

const between = (text, startToken, endToken) => {
  const start = text.indexOf(startToken);
  assert.ok(start >= 0, `missing ${startToken}`);
  const end = text.indexOf(endToken, start);
  assert.ok(end > start, `missing ${endToken} after ${startToken}`);
  return text.slice(start, end);
};

const count = (text, pattern) => (text.match(pattern) || []).length;

// Assertions about what the CODE does must not read the prose that explains it
// — these components document the treatments they deliberately do NOT use.
const code = (text) =>
  text
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, "")
    .replace(/^\s*\/\/.*$/gm, "");

// ===========================================================================
// A. Simulation sub-tab navigation
// ===========================================================================

const simulationTabs = between(source, 'value: "outcome-distribution"', "/>");

test("all six simulation views remain, in order, with unchanged values", () => {
  const expected = [
    ["outcome-distribution", "Outcome Distribution", "Outcomes"],
    ["historical-trend", "Opening Profit vs Cost", "OPvC"],
    ["simulation-drivers", "Simulation Drivers", "Drivers"],
    ["value-contribution", "Value Structure", "Value"],
    ["pack-breakdown", "Pack Paths", "Paths"],
    ["simulation-metrics", "Metrics", "Metrics"],
  ];
  let cursor = -1;
  for (const [value, label, shortLabel] of expected) {
    const index = simulationTabs.indexOf(`value: "${value}", label: "${label}", shortLabel: "${shortLabel}"`);
    assert.ok(index >= 0, `${label} must remain, with its short label`);
    assert.ok(index > cursor, `${label} must keep its position in the order`);
    cursor = index;
  }
  assert.equal(count(simulationTabs, /value: "/g), 6, "no view was added or dropped");
});

test("the short label is visible below desktop and the full name is the accessible name", () => {
  const button = between(segmented, "const shortLabel = option?.shortLabel", "</button>");

  // Full name at 1200px+, abbreviation below it — one control, two faces.
  assert.ok(segmented.includes('<span className="hidden whitespace-nowrap desk:block">{option?.label ?? optionValue}</span>'));
  assert.ok(segmented.includes('<span className="block whitespace-nowrap desk:hidden">{shortLabel}</span>'));
  // The abbreviation is never what a screen reader hears.
  assert.ok(button.includes("aria-label={accessibleName}"));
  assert.ok(segmented.includes("option?.ariaLabel || (shortLabel ? option?.label : undefined)"));
  assert.ok(segmented.includes("option?.title || (shortLabel ? option?.label : undefined)"), "and the tooltip carries it too");
  // No option without a short label changes behaviour at all.
  assert.ok(segmented.includes('<span className="block truncate">{option?.label ?? optionValue}</span>'), "the default face is unchanged");
});

test("the six controls scroll on one line instead of truncating", () => {
  assert.ok(source.includes("mobileScroll"), "the simulation strip opts in");
  const tabsCall = between(source, '<SectionViewTabs\n                      className="mb-4"', "/>");
  assert.ok(tabsCall.includes("mobileScroll"), "the six-way strip is the caller that opts in");

  const row = between(segmented, "className={`inline-flex max-w-full items-center", "role=");
  assert.ok(row.includes("max-desk:overflow-x-auto"), "the options scroll inside the pill");
  // The full-width band was narrowed to phones by the cleanup pass — from 600px
  // up the pill shrinks to its content instead. See
  // SimulationResultsMobileCleanup.contract.test.mjs, which owns that decision.
  assert.ok(row.includes("max-tab:w-full"));
  assert.ok(/\[scrollbar-width:none\]|::-webkit-scrollbar/.test(row), "no scrollbar chrome inside a pill");
  // Options must not shrink, and must not clip.
  assert.ok(segmented.includes("max-desk:shrink-0"), "an option keeps at least its natural width");
  const shortLabelBranch = code(between(segmented, "{shortLabel ? (", ") : ("));
  assert.ok(!shortLabelBranch.includes("truncate"), "a short label is never truncated");
  assert.ok(shortLabelBranch.includes("whitespace-nowrap"), "it stays on one line at its full length");
  assert.ok(segmented.includes("max-desk:min-h-9"), "the option keeps a touch-sized target");
});

test("the active control is scrolled back into view without moving the page", () => {
  const effect = between(segmented, "useEffect(() => {\n    if (!mobileScroll) return;", "}, [value, mobileScroll]);");
  assert.ok(effect.includes("row.scrollLeft"), "horizontal scroll only");
  assert.ok(
    !effect.includes("scrollIntoView"),
    "scrollIntoView would also scroll the page vertically under the sticky tab bar"
  );
  assert.ok(effect.includes("data-segment-value"), "it finds the active option by its own marker");
});

test("keyboard navigation and single-mount behaviour are unchanged", () => {
  // Arrow/Home/End roving focus predates this pass and must survive it.
  assert.ok(segmented.includes('["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"]'));
  assert.ok(segmented.includes('role="radiogroup"'));
  assert.ok(segmented.includes('role="radio"'));
  assert.ok(segmented.includes("tabIndex={isActive ? 0 : -1}"));
  // One strip, one mounted view: the sub-tabs are still a single chain of
  // ternaries over `activeInsightsGraphMode`, not six mounted panels.
  assert.equal(count(source, /<SectionViewTabs\n {22}className="mb-4"/g), 1);
});

// ===========================================================================
// B. Outcome Distribution
// ===========================================================================

test("the below-desktop axis flag is its own boundary, not the chart's 767px one", () => {
  // `isMobile` drives tick density and marker layout — approved graph behaviour
  // this pass does not touch. Axis suppression is a below-DESKTOP decision.
  assert.ok(chart.includes('window.matchMedia("(max-width: 767px)")'), "the existing flag is untouched");
  assert.ok(chart.includes('window.matchMedia("(max-width: 1199.98px)")'), "the new flag uses the project boundary");
  assert.ok(chart.includes("const [isBelowDesktop, setIsBelowDesktop] = useState(false);"));
});

test("mobile renders no Y-axis tick labels and reserves no width for them", () => {
  const rightAxis = between(chart, '<YAxis\n              yAxisId="right"', "/>");
  assert.ok(rightAxis.includes("width={isBelowDesktop ? 0 : 44}"), "no reserved width below desktop");
  assert.ok(
    rightAxis.includes("tick={isBelowDesktop ? false : { fill: \"var(--text-secondary)\", fontSize: 11 }}"),
    "no tick labels below desktop"
  );
  // Desktop keeps its 44px axis and its ticks.
  assert.ok(rightAxis.includes("44"), "desktop keeps the percentage axis");
  assert.ok(rightAxis.includes('tickFormatter={(v) => `${Number(v).toFixed(0)}%`}'), "and its formatter");

  // The left axis never drew ticks; below desktop it also gives up its gutter.
  const leftAxis = between(chart, '<YAxis\n              yAxisId="left"', "/>");
  assert.ok(leftAxis.includes("width={isBelowDesktop ? 0 : 12}"));
  assert.ok(leftAxis.includes("tick={false}"));

  // The recovered width actually reaches the plot.
  assert.ok(chart.includes("margin={isBelowDesktop ? { top: 8, right: 8, left: 0, bottom: 8 } : { top: 8, right: 56, left: 4, bottom: 8 }}"));
});

test("the scale, the curve and the X axis are untouched", () => {
  const rightAxis = between(chart, '<YAxis\n              yAxisId="right"', "/>");
  // The axis still EXISTS and still declares its domain: suppressing ticks is
  // not the same as removing the scale the line is plotted against.
  assert.ok(rightAxis.includes("domain={[0, 100]}"), "the 0-100 scale survives");
  assert.ok(chart.includes('yAxisId="right"\n                type="monotone"\n                dataKey="chance_to_reach_percent"'));
  // X axis, bars, line, tooltip and both series identities are unchanged.
  const xAxis = between(chart, "<XAxis", "/>");
  assert.ok(xAxis.includes('dataKey="x_slot"'));
  assert.ok(xAxis.includes("tick={{ fill: \"var(--text-secondary)\", fontSize: 11 }}"), "outcome labels still render");
  assert.ok(!xAxis.includes("isBelowDesktop"), "the X axis is not touched by this pass");
  assert.ok(chart.includes("<Tooltip content={<CombinedTooltip />}"), "exact values stay in the tooltip");
  assert.ok(chart.includes("Frequency Shape"));
  assert.ok(chart.includes("Chance To Reach"));
});

test("marker chips are label-only below desktop and keep every option", () => {
  const chip = between(chart, "data-distribution-marker-chip", "</button>");

  assert.ok(chip.includes('<span className="whitespace-nowrap desk:hidden">{marker.label}</span>'), "label only below desktop");
  assert.ok(
    chip.includes('<span className="hidden desk:inline">'),
    "the label + value face is desktop only"
  );
  assert.ok(chip.includes("formatCompactCurrency(marker.value)"), "desktop still prints the value");
  // Nothing is filtered: the same rows the chart already built become chips.
  assert.ok(chart.includes("{markerRows.map((marker) => ("));
  assert.ok(!/markerRows[\s\S]{0,80}\.slice\(/.test(chart), "no option is dropped below desktop");
  // The value stays reachable at every width.
  assert.ok(chart.includes("aria-label={`${marker.label}: ${formatCompactCurrency(marker.value)}`}"));
  assert.ok(chart.includes("title={`${marker.label}: ${formatCompactCurrency(marker.value)}`}"));
  // 44px became 40px in the cleanup pass, where the chip also became a
  // full-width cell of a two-column grid. That file owns the exact figure.
  assert.ok(chip.includes("max-desk:min-h-10"), "a label-only chip still has a touch target");
});

test("one compact active-value readout replaces the per-chip numbers", () => {
  const readout = between(chart, "data-distribution-active-readout", "</p>");
  assert.ok(readout.includes("desk:hidden"), "below desktop only");
  assert.ok(readout.includes('aria-live="polite"'));
  assert.ok(readout.includes("{activeMarker.label}"));
  assert.ok(readout.includes("formatCompactCurrency(activeMarker.value)"));
  assert.equal(count(code(chart), /data-distribution-active-readout/g), 1, "one readout, not a row of cards");
  // Selecting still drives the chart exactly as before.
  assert.ok(chart.includes("onClick={() => onMarkerClick(marker.key)}"));
  assert.ok(chart.includes("setActiveMarkerKey((current) => (current === markerKey ? null : markerKey))"));
});

// ===========================================================================
// C. Simulation Drivers
// ===========================================================================

const driversList = between(source, "function SimulationDriversCompactList(", "function TopEVDriversContent(");

test("drivers render as compact ranked rows below desktop and cards at 1200px+", () => {
  assert.ok(driversList.includes('data-simulation-drivers-compact className="min-w-0 desk:hidden"'));
  assert.ok(source.includes('<div className="hidden min-w-0 gap-x-5 desk:grid lg:grid-cols-2">'), "the desktop tree is desktop only");
  assert.ok(source.includes("<SimulationDriversCompactList hits={hits} totalEV={totalEV} />"));
  // Rank / name / value on one grid, dividers instead of cards.
  assert.ok(driversList.includes("grid-cols-[1.5rem_minmax(0,1fr)_4.5rem]"));
  assert.ok(driversList.includes("min-h-11"), "44px touch target");
  assert.ok(!/rounded-(?:lg|xl|2xl)/.test(code(driversList)), "no row may draw a card");
  assert.ok(driversList.includes("border-b border-l-2 border-[var(--border-subtle)]"), "thin dividers");
});

test("every driver, its order and its values are unchanged", () => {
  // The list maps `hits` in place — the same array, already sliced to maxRows
  // by the caller, in the backend's order.
  assert.ok(driversList.includes("const rows = hits.map((hit, index) => {"));
  assert.ok(driversList.includes("rank: index + 1"));
  assert.ok(!driversList.includes("sort("), "ordering is the backend's");
  assert.ok(!/hits\.(?:filter|slice)\(/.test(driversList), "no driver is dropped");
  // The share expression is the desktop one, on the same two backend fields.
  const shareExpression = "ev !== null && totalEV !== null && totalEV > 0 ? `${((ev / totalEV) * 100).toFixed(1)}%` : null";
  assert.ok(driversList.includes(shareExpression));
  assert.ok(count(source, /ev !== null && totalEV !== null && totalEV > 0/g) >= 2, "both trees compute share identically");
  assert.ok(driversList.includes("getTopHitNearMintPrice(hit)"), "the same price accessor");
});

test("one shared detail region carries the selected driver's supporting values", () => {
  assert.equal(count(code(driversList), /data-simulation-driver-detail/g), 1);
  assert.equal(count(code(source), /data-simulation-driver-detail/g), 1, "and only one on the page");
  const detail = between(driversList, "id={detailRegionId}", "</div>");
  assert.ok(detail.includes('aria-live="polite"'));
  assert.ok(detail.includes("COMPACT_DETAIL_CLASS"), "the shared rail treatment");
  // Market Price is the one supporting value the ranked row does not already
  // carry, and it is what this region is now for. The value contribution, the
  // share, the thumbnail and the price caveat were dropped by the cleanup pass
  // BECAUSE the row above states the first two and the desktop card still
  // states all four — see SimulationResultsMobileCleanup.contract.test.mjs,
  // which owns that removal and asserts the desktop tree kept every field.
  assert.ok(driversList.includes('label="Market Price"'));
});

test("the driver list defaults to the highest driver and is keyboard operable", () => {
  assert.ok(driversList.includes("useState(0)"), "the first (highest) driver is selected by default");
  assert.ok(driversList.includes("<button"), "a real button, so Enter and Space come free");
  assert.ok(driversList.includes('type="button"'));
  assert.ok(driversList.includes("focus-visible:ring-2"));
  assert.ok(driversList.includes("aria-expanded={isSelected}"));
  assert.ok(driversList.includes("aria-controls={detailRegionId}"));
  assert.equal(count(code(driversList), /useId\(\)/g), 1, "one region id, not one per row");
  assert.ok(driversList.includes("COMPACT_ROW_SELECTED_CLASS"), "the shared selected treatment");
});

test("the drivers intro shrinks without losing its meaning", () => {
  const intro = between(source, "<SimulationResultsPanel id=\"set-detail-simulation-drivers\">", "<TopEVDriversContent");
  assert.ok(intro.includes("<InterpretationInsight"), "the interpretation still renders");
  assert.ok(intro.includes("sectionMeta={topEvDriversMeta}"), "from the same backend meta");
  assert.ok(intro.includes("Simulated Expected Value"), "the headline figure stays");
  assert.ok(intro.includes("max-desk:"), "only its size and spacing move below desktop");
  assert.ok(!intro.includes("desk:hidden"), "no copy is removed below desktop");
});

// ===========================================================================
// D. Pack Paths
// ===========================================================================

test("the three approved summary chips are hidden below 1200px only", () => {
  const approved = between(source, "const PACK_PATH_DESKTOP_ONLY_EVIDENCE = new Set([", "]);");
  for (const label of ["dominant path", "dominant path share", "special path share"]) {
    assert.ok(approved.includes(`"${label}"`), `${label} is an approved mobile removal`);
  }
  assert.equal(count(approved, /"/g), 6, "exactly three labels, and no others");

  // Hidden per chip, by label — the rows are still built.
  assert.ok(source.includes("PACK_PATH_DESKTOP_ONLY_EVIDENCE.has(String(label).toLowerCase()) ? \" max-desk:hidden\" : \"\""));
  assert.ok(source.includes("data-pack-path-evidence-chip={String(label).toLowerCase()}"));
  // A chip that is not on the list still renders at every width.
  assert.ok(source.includes("{evidenceRows.map(([label, value]) => ("), "the map is unchanged");
});

test("no Pack Paths data or calculation was removed", () => {
  const builder = between(source, "function getPackPathEvidenceRowsFromCounts(", "function buildNormalStateContributionRows(");
  assert.ok(builder.includes('evidenceRows.push(["Dominant path", dominant.name]);'));
  assert.ok(builder.includes('evidenceRows.push(["Dominant path share"'));
  assert.ok(builder.includes('evidenceRows.push(["Special path share"'));
  assert.ok(!builder.includes("max-desk"), "the selector knows nothing about breakpoints");
  // The path visualisation, its legend and its tooltip are untouched.
  const packPaths = between(source, "function PackPathsVisualization(", "function RarityContributionRails(");
  // Insights passes `condensed`, and that branch delegates straight to the
  // visualization above — so this IS the Pack Paths the set page renders.
  assert.ok(
    source.slice(source.indexOf("function PackBreakdownContent(")).slice(0, 600).includes("<PackPathsVisualization"),
    "the condensed Insights path renders the visualization asserted here"
  );
  assert.ok(packPaths.includes("<PieChart>"));
  assert.ok(packPaths.includes("<PackPathDonutTooltip totalPacks={totalPacks} />"));
  assert.ok(packPaths.includes("{pathRows.map((row) => ("), "every configured path stays in the legend");
  assert.ok(packPaths.includes("formatShareFromCounts(row.count, totalPacks)"), "with its real share");
  assert.ok(packPaths.includes("<NormalStateContributionRails"));
});

test("desktop still renders all three summary chips", () => {
  const chips = between(source, "data-pack-path-evidence-chip", "</span>");
  assert.ok(chips.includes("{label}") || chips.includes("{String(value)}"));
  // The suppression is expressed only as a max-desk: utility, so 1200px+ can
  // not be reached by it.
  const chipBlock = between(source, "{evidenceRows.map(([label, value]) => (", "))}");
  assert.ok(chipBlock.includes("max-desk:hidden"));
  assert.ok(!/(^|[\s"`])desk:hidden/.test(chipBlock), "nothing hides these on desktop");
});

// ===========================================================================
// E. Metrics
// ===========================================================================

const metricsList = between(source, "function SimulationMetricsCompactList(", "function SimulationMetricsContent(");
const metricsContent = between(source, "function SimulationMetricsContent(", "function formatDriverScore(");

test("Metrics renders compact rows below desktop and its cards at 1200px+", () => {
  assert.ok(metricsList.includes('data-simulation-metrics-compact className="min-w-0 desk:hidden"'));
  assert.ok(metricsContent.includes('<div className="hidden space-y-3 desk:block">'), "the card layout is desktop only");
  assert.ok(metricsContent.includes("<SimulationMetricsCompactList groups={metricGroups} />"));
  assert.ok(metricsList.includes("grid-cols-[minmax(0,1fr)_5.5rem]"), "one grid so values align");
  assert.ok(metricsList.includes("min-h-11"));
  assert.ok(!/rounded-(?:lg|xl|2xl)/.test(code(metricsList)), "no nested mini-cards");
});

test("every metric group survives, in the desktop order, with its default selection", () => {
  const groups = between(metricsContent, "const metricGroups = [", "];");
  const expected = [
    ["where-packs-land", "Where Packs Land"],
    ["will-i-lose-money", "Will I lose money?"],
    ["whats-the-upside", "What's the upside?"],
    ["how-swingy", "How swingy is it?"],
    ["how-simulated", "How was this simulated?"],
  ];
  let cursor = -1;
  for (const [key, label] of expected) {
    const index = groups.indexOf(`key: "${key}"`);
    assert.ok(index >= 0, `${label} must remain`);
    assert.ok(index > cursor, `${label} keeps its position`);
    cursor = index;
    assert.ok(groups.includes(`label: "${label}"`) || groups.includes(`label: "${label.replace("'", "\\'")}"`));
  }
  // "Where the pack lands" is the default.
  assert.ok(metricsList.includes("useState(groups[0]?.key || null)"));
  assert.ok(groups.indexOf('key: "where-packs-land"') < groups.indexOf('key: "will-i-lose-money"'));
});

test("both presentations render the identical rows, from one definition", () => {
  // Each group's lines are hoisted into a const and handed to BOTH trees, so a
  // row cannot exist on one and not the other.
  for (const body of ["packsLandBody", "loseMoneyLines", "upsideLines", "swingyLines", "howSimulatedLines"]) {
    assert.ok(metricsContent.includes(`const ${body} = (`), `${body} is defined once`);
    assert.equal(
      count(metricsContent, new RegExp(`\\{${body}\\}`, "g")),
      1,
      `${body} is placed into the desktop card exactly once`
    );
    assert.ok(metricsContent.includes(`body: ${body}`), `${body} is what the compact list shows too`);
  }
  // Spot-check that the full row inventory is still present.
  for (const label of [
    "EV / Cost",
    "Chance to Beat Pack Cost",
    "Expected Loss / Pack",
    "Chance at Big Pull",
    "Non-hit EV",
    "Coefficient of Variation",
    "Top 5 Share",
    "Pack Market Price",
    "Model Agreement",
    "Simulated Set Value Cards",
  ]) {
    assert.ok(metricsContent.includes(`label="${label}"`), `${label} must remain`);
  }
  assert.ok(metricsContent.includes("buildPercentileStripModel"), "the percentile strip is still computed from live values");
  assert.ok(metricsContent.includes("<PercentileStripChart model={stripModel} />"));
});

test("exactly one shared Metrics detail region, defaulting open on the first group", () => {
  assert.equal(count(code(metricsList), /data-simulation-metric-detail/g), 1);
  assert.equal(count(code(source), /data-simulation-metric-detail/g), 1, "and only one on the page");
  const detail = between(metricsList, "id={detailRegionId}", "</div>");
  assert.ok(detail.includes('aria-live="polite"'));
  assert.ok(detail.includes("COMPACT_DETAIL_CLASS"));
  assert.ok(metricsList.includes("{selected.body}"), "the selected group's complete content");
  assert.ok(metricsList.includes("{selected.infoText ? <InfoPopover"), "info tooltips survive");
  assert.ok(metricsList.includes('<div className="inline-flex min-w-0 items-center gap-1.5'), "the shared header wrapper is a div, not a paragraph");
  assert.ok(!metricsList.includes('<p className="inline-flex min-w-0 items-center gap-1.5'), "the invalid paragraph wrapper is gone");
  assert.ok(!/groups\.map[\s\S]{0,400}\{group\.body\}/.test(metricsList), "the list never renders every body at once");
});

test("Metrics rows are keyboard operable and reuse the shared selected treatment", () => {
  assert.ok(metricsList.includes("<button"));
  assert.ok(metricsList.includes('type="button"'));
  assert.ok(metricsList.includes("focus-visible:ring-2"));
  assert.ok(metricsList.includes("aria-expanded={isSelected}"));
  assert.ok(metricsList.includes("aria-controls={detailRegionId}"));
  assert.equal(count(code(metricsList), /useId\(\)/g), 1);
  assert.ok(metricsList.includes("COMPACT_ROW_SELECTED_CLASS"));
  assert.ok(metricsList.includes("COMPACT_ROW_IDLE_CLASS"));
  // The qualitative tag is the SAME badge the desktop row draws.
  assert.ok(metricsList.includes("<SimMetricTag tag={group.tag} />"));
  assert.ok(source.includes("function SimMetricTag({ tag })"));
  assert.ok(between(source, "function SimMetricRow(", "\n}").includes("<SimMetricTag tag={tag} />"));
});

test("Metrics introduces no request path and no new arithmetic", () => {
  const tree = code(metricsList);
  assert.ok(!/\bfetch\(|axios|useSWR|getPokemonSet/.test(tree), "no request path");
  assert.ok(!/useEffect/.test(tree), "no lifecycle work");
  // Every scan value is a formatter call on an existing field, not a new
  // computation performed for the row.
  const groups = between(metricsContent, "const metricGroups = [", "];");
  for (const expression of [
    "value: money(p50)",
    "value: probability(safeSummary.prob_profit)",
    "value: probability(safeSummary.prob_big_hit)",
    "value: formatMetricNumber(safeSummary.coefficient_of_variation, 2)",
    "value: countValue(simulationCount)",
  ]) {
    assert.ok(groups.includes(expression), `${expression} reuses an existing formatted field`);
  }
});

// ===========================================================================
// F. The shared selected-row treatment
// ===========================================================================

test("one selected/idle treatment is shared by all three compact lists", () => {
  const selectedClass = between(source, "const COMPACT_ROW_SELECTED_CLASS =", ";");
  const idleClass = between(source, "const COMPACT_ROW_IDLE_CLASS =", ";");

  assert.ok(selectedClass.includes("compact-row-selected"), "the glow comes from one CSS rule");
  assert.ok(selectedClass.includes("border-l-[var(--accent)]"), "the accent rail");
  assert.ok(
    selectedClass.includes("bg-[var(--surface-page)]"),
    "an OPAQUE base, so a chart behind the list cannot read through the selected row"
  );
  assert.ok(idleClass.includes("border-l-transparent"), "selection changes a colour, never a position");

  // All three lists use it — no list may invent its own selected style.
  // RipBreakdownCompactRow is gone with the RIP Score Breakdown compact feed;
  // the two surviving compact lists still share one treatment.
  for (const list of ["SimulationDriversCompactList", "SimulationMetricsCompactList"]) {
    const start = source.indexOf(`function ${list}(`);
    assert.ok(start >= 0, `${list} must exist`);
    const tree = source.slice(start, start + 6000);
    assert.ok(tree.includes("COMPACT_ROW_SELECTED_CLASS"), `${list} uses the shared selected treatment`);
    assert.ok(tree.includes("COMPACT_ROW_IDLE_CLASS"), `${list} uses the shared idle treatment`);
  }
});

test("the glow is restrained, below-desktop only and reduced-motion safe", () => {
  const mobileBlock = globals.slice(globals.indexOf("@media (max-width: 1199.98px) {"));
  const rule = between(mobileBlock, ".compact-row-selected {", "}");

  assert.ok(rule.includes("background-image: linear-gradient("), "an accent tint over the opaque base");
  assert.ok(rule.includes("box-shadow:"), "a restrained bloom plus a rail halo");
  assert.ok(rule.includes("var(--accent)"), "the app's own accent, not a new palette");
  assert.ok(!/rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+/.test(rule), "no hardcoded colour may bypass the theme tokens");
  assert.ok(!rule.includes("animation"), "no continuous animation");
  assert.ok(!rule.includes("filter:"), "no viewport-wide blur");

  // The halo is clipped to the rail: a blur wider than the negative spread
  // would bloom into a perimeter outline around the whole row.
  const halo = rule.match(/-?\d+px 0 (\d+)px -(\d+)px/);
  assert.ok(halo, "the rail halo is an offset, blurred, negatively-spread shadow");
  assert.ok(Number(halo[1]) - Number(halo[2]) <= 0, "blur must not exceed the spread, or it outlines the row");

  // Both the rule and the detail rail live below 1200px, and reduced motion
  // removes the transition.
  assert.ok(mobileBlock.includes(".compact-row-detail {"));
  assert.ok(mobileBlock.includes("@media (prefers-reduced-motion: reduce)"));
  assert.ok(between(mobileBlock, "@media (prefers-reduced-motion: reduce) {", "}").includes(".compact-row-selected"));
  assert.ok(!globals.includes("\n.compact-row-selected {"), "the rule is never declared unscoped");
});

// ===========================================================================
// G. Collector Profile
// ===========================================================================

const collectorSection = between(source, "function CollectorProfileSection(", "const TOP_CARD_IMAGE_CONTAINER_CLASS");
const collectorStage = between(source, "function CollectorProfileStage(", "// The connector between stages");

test("the three-stage summary compacts without dropping a field", () => {
  // One compact grid row per stage below desktop: label + score on line one,
  // meta under the label, note across the foot.
  assert.ok(collectorStage.includes("max-desk:grid"));
  assert.ok(collectorStage.includes("max-desk:grid-cols-[minmax(0,1fr)_auto]"));
  assert.ok(collectorStage.includes("max-desk:col-span-2"), "the note runs the full width");
  assert.ok(collectorStage.includes("max-desk:text-xl"), "the 28px score steps down, it does not disappear");
  // All four fields still render.
  for (const field of ["{label}", "{value}", "{meta || \" \"}", "{note}"]) {
    assert.ok(collectorStage.includes(field), `${field} must remain`);
  }
  assert.ok(collectorStage.includes("<InfoPopover text={infoBullets(bullets)} />"), "the full copy stays in the tooltip");
  // Desktop is untouched.
  assert.ok(collectorStage.includes("text-[1.75rem]"), "desktop keeps the large score");
  assert.ok(collectorStage.includes("lg:w-[17rem]"), "desktop keeps its fixed measure");
});

test("the flow keeps its order and connectors and loses only its box", () => {
  const flow = between(collectorSection, "data-collector-profile-flow", ">");
  for (const stripped of ["max-desk:rounded-none", "max-desk:border-0", "max-desk:bg-transparent", "max-desk:px-0", "max-desk:py-0"]) {
    assert.ok(flow.includes(stripped), `the flow must drop ${stripped.replace("max-desk:", "")}`);
  }
  assert.ok(flow.includes("rounded-xl border border-[var(--border-subtle)]"), "desktop keeps the panel");

  // Order and connectors intact.
  const order = ["Set Desirability", "Collector Appeal", "RIP Score Contribution"];
  let cursor = -1;
  for (const label of order) {
    const index = collectorSection.indexOf(`label="${label}"`);
    assert.ok(index > cursor, `${label} keeps its place in the chain`);
    cursor = index;
  }
  assert.equal(count(collectorSection, /<CollectorProfileArrow \/>/g), 2, "both connectors survive");
  const arrow = between(source, "function CollectorProfileArrow(", "\n}");
  assert.ok(arrow.includes("max-desk:h-3"), "the connector shrinks rather than disappearing");
  assert.ok(arrow.includes("max-desk:py-0"));
});

test("Collector Profile keeps every score, rank, contribution and description", () => {
  assert.ok(collectorSection.includes("value={desirability.available ? desirability.scoreLabel"));
  assert.ok(collectorSection.includes("meta={desirability.available ? desirability.rankLabel : null}"));
  assert.ok(collectorSection.includes("Supporting input — no RIP Score weight of its own."));
  assert.ok(collectorSection.includes("value={opening.available ? collectorAppeal.scoreLabel"));
  assert.ok(collectorSection.includes("`${collectorAppeal.tier} Tier`"));
  assert.ok(collectorSection.includes("collectorAppeal.rankLabel"));
  assert.ok(collectorSection.includes("Roster demand through the modeled opening paths."));
  assert.ok(collectorSection.includes('value={ripContribution?.weightLabel || "10%"}'));
  assert.ok(collectorSection.includes("meta={ripContribution?.contributionPointsLabel || null}"), "the model points remain");
  assert.ok(collectorSection.includes("RIP Core supplies the other 90%."));
  // Views, controls and every deep-link anchor.
  assert.ok(collectorSection.includes('label: "Roster Appeal"'));
  assert.ok(collectorSection.includes('label: "Opening Paths"'));
  assert.ok(collectorSection.includes("<CollectorRosterAppealPanel"));
  assert.ok(collectorSection.includes("<CollectorOpeningPathsPanel"));
  assert.ok(collectorSection.includes("loading={loading}"), "loading states preserved");
  assert.ok(collectorSection.includes("loadingTimedOut={loadingTimedOut}"));
});

test("the Roster Appeal and Opening Paths panels flatten without losing content", () => {
  const panel = between(source, "function CollectorPanel(", "\n}");
  assert.ok(panel.includes("divide-y divide-[var(--border-subtle)]"), "dividers survive");
  for (const stripped of ["max-desk:rounded-none", "max-desk:border-0", "max-desk:bg-transparent"]) {
    assert.ok(panel.includes(stripped), `the panel must drop ${stripped.replace("max-desk:", "")}`);
  }
  assert.ok(panel.includes("rounded-xl border border-[var(--border-subtle)]"), "desktop keeps the panel");

  // Every Roster Appeal metric and the driver list.
  const roster = between(source, "function CollectorRosterAppealPanel(", "function CollectorOpeningPathsPanel(");
  assert.ok(roster.includes('title="Roster Quality"'));
  assert.ok(roster.includes("{presentation.components.map((component) => ("), "every roster-quality component");
  assert.ok(roster.includes('title="Demand Distribution"'));
  assert.ok(roster.includes('label="Effective Subjects"'));
  assert.ok(roster.includes('label="Top Subject Share"'));
  assert.ok(roster.includes('label="Top 3 Share"'));
  assert.ok(roster.includes('title="Top Desirability Drivers"'));
  assert.ok(roster.includes("<SetDesirabilitySubjectRow"));
  assert.ok(roster.includes("position={index + 1}"), "the ranked ordinal survives");

  // Every Opening Paths field.
  const paths = between(source, "function CollectorOpeningPathsPanel(", "function CollectorProfileSection(");
  assert.ok(paths.includes('title="Opening Structure"'));
  assert.ok(paths.includes('label="Dual-Path Depth"'));
  assert.ok(paths.includes('label="Chase Appeal"'));
  assert.ok(paths.includes("subjects with multiple paths"));
  assert.ok(paths.includes('title="Pull paths for top subjects"'));
  assert.ok(paths.includes("<OpeningExperienceSubjectRow"));
  const subjectRow = between(source, "function OpeningExperienceSubjectRow(", "\n}");
  assert.ok(subjectRow.includes('kind="Accessible Path"'), "the Access path survives");
  assert.ok(subjectRow.includes('kind="Elite Chase"'), "the Elite path survives");
  assert.ok(subjectRow.includes("% of roster demand"));
});

test("narrow phones get two metric columns instead of three unreadable ones", () => {
  const row = between(source, "function CollectorMetricRow(", "\n}");
  assert.ok(row.includes("max-tab:grid-cols-2"), "three columns drop to two below the 600px boundary");
  assert.ok(row.includes("grid-cols-3"), "and are three from 600px up, desktop included");
  assert.ok(row.includes('columns === 2 ? "grid-cols-2"'), "an explicit two-column band is unchanged");
});

// ===========================================================================
// H. Desktop protection
// ===========================================================================

test("every change in this pass is expressed below 1200px", () => {
  // Nothing may hide a desktop element or restyle one unconditionally. Each
  // tree below is checked for `desk:hidden` on content that must survive at
  // 1200px+, and for max-desk/desk scoping on the rest.
  for (const [name, tree] of [
    ["the drivers compact list", driversList],
    ["the metrics compact list", metricsList],
    ["the collector stage", collectorStage],
  ]) {
    assert.ok(/max-desk:|desk:hidden/.test(tree), `${name} is scoped to a breakpoint`);
  }
  // The two compact lists are the below-desktop tree, so they carry desk:hidden
  // and need no internal desktop styling.
  assert.ok(driversList.includes("desk:hidden"));
  assert.ok(metricsList.includes("desk:hidden"));
  assert.ok(!/(^|[\s"`])sm:/.test(code(driversList)), "no band-scoped style max-desk cannot outrank");
  assert.ok(!/(^|[\s"`])sm:/.test(code(metricsList)));

  // The chart's axis suppression is the only chart change and it is flag-gated:
  // one declaration, one matchMedia effect, and the three places it is read
  // (chart margin, left axis width, right axis width + tick).
  // Five reads of the flag: the useState declaration, the chart margin, the
  // left axis width, and the right axis's width and tick. `setIsBelowDesktop`
  // is a distinct identifier (capital I) and is counted separately.
  assert.equal(count(chart, /isBelowDesktop/g), 5, "the flag is used only where this pass says it is");
  assert.equal(count(chart, /setIsBelowDesktop/g), 3, "declared once, set on mount and on change");
});

test("no dependency was added and no data path changed", () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(here, "../../package.json"), "utf8"));
  const deps = { ...pkg.dependencies, ...pkg.devDependencies };
  assert.ok(deps.recharts, "recharts is still the chart library");
  assert.ok(!deps["react-window"] && !deps["framer-motion"], "no list/animation dependency was introduced");
  // The compact lists take data as props and never fetch.
  for (const tree of [code(driversList), code(metricsList)]) {
    assert.ok(!/\bfetch\(|axios|useSWR|getPokemonSet/.test(tree));
  }
});
