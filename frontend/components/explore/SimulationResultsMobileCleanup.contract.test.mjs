// Simulation Results below 1200px — the final cleanup pass.
//
// Four remaining defects, and nothing else:
//
//   1. The six-way sub-tab strip stretched to the full block width but its pills
//      kept their natural size, so the pill background ran out to the right with
//      nothing in it. Below 600px the options now grow into that space; from
//      600px to 1199px the strip shrinks to its content the way 1200px+ already
//      does. Either way the row ends where the controls end.
//   2. The "raw evidence" subtitle repeated the section eyebrow and cost a line
//      of a phone screen. Hidden below desktop; the string is untouched.
//   3. Outcome Distribution spent ~30px of dead space between the plot and its
//      marker selectors, then wrapped eight 44px chips raggedly. The gap
//      collapses and the chips become a two-column grid on phones.
//   4. Simulation Drivers' detail panel restated the row it was opened from —
//      value, share, a thumbnail and a generic price caveat. Only Market Price
//      is information the list does not already carry, so only Market Price
//      stays.
//
// Every removal below is asserted to be a below-1200px VISIBILITY change with
// the desktop tree still rendering the field, EXCEPT the four driver-detail
// removals, which are deletions from a `desk:hidden` subtree that has no
// desktop counterpart — the desktop driver card is a separate component and is
// asserted here to still carry every one of them.
//
// RipStatisticsPageClient.jsx cannot be imported outside the Next build (it uses
// extensionless "@/..." specifiers only the bundler resolves), so the structural
// assertions read the rendered JSX source, matching every other contract test
// for this page. The file carries mixed CRLF/LF, so it is normalised before any
// multi-line anchor is searched for.

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

const segmentedRow = between(segmented, "className={`inline-flex max-w-full items-center", "role=");
const segmentedOption = between(segmented, "data-segment-value={optionValue}", "{shortLabel ? (");

// ===========================================================================
// 1. The simulation sub-tab strip fills its row
// ===========================================================================

test("the six controls, their order and their values are exactly what they were", () => {
  const simulationTabs = between(source, 'value: "outcome-distribution"', "/>");
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
    const index = simulationTabs.indexOf(
      `value: "${value}", label: "${label}", shortLabel: "${shortLabel}"`
    );
    assert.ok(index >= 0, `${label} must remain, with its short label`);
    assert.ok(index > cursor, `${label} must keep its position in the order`);
    cursor = index;
  }
  assert.equal(count(simulationTabs, /value: "/g), 6, "no view was added or dropped");
});

test("phones stretch the strip and let the options grow into it", () => {
  // Below 600px the strip is a block-level flex row at the full block width and
  // each option takes an equal share of whatever is left over — that share is
  // the space that used to sit empty on the right.
  assert.ok(segmentedRow.includes("max-tab:flex"), "block-level flex on phones");
  assert.ok(segmentedRow.includes("max-tab:w-full"), "the strip spans the block on phones");
  assert.ok(segmentedOption.includes("max-tab:grow"), "each option absorbs an equal share of the slack");
});

test("tablets shrink the strip to its content instead of stretching it", () => {
  // 600-1199px keeps the base `inline-flex`, so the pill ends where the last
  // option ends — the same shrink-to-fit strip 1200px+ has always drawn. A
  // full-width strip here would only move the empty zone, not remove it.
  assert.ok(
    !segmentedRow.includes("max-desk:w-full"),
    "the strip must not be forced to full width across the whole tablet band"
  );
  assert.ok(
    !segmentedRow.includes("max-desk:flex "),
    "nor made block-level across it, which fills the line box even without w-full"
  );
  assert.ok(segmentedRow.includes("inline-flex"), "the base is still shrink-to-fit");
});

test("no option may shrink, so no label is clipped or ellipsised at any width", () => {
  assert.ok(segmentedOption.includes("max-desk:shrink-0"), "an option keeps at least its natural width");
  assert.ok(!code(segmentedOption).includes("flex-none"), "flex-none would also refuse to grow");
  const shortLabelBranch = code(between(segmented, "{shortLabel ? (", ") : ("));
  assert.ok(!shortLabelBranch.includes("truncate"), "a short label is never truncated");
  assert.ok(!shortLabelBranch.includes("text-ellipsis"));
  assert.ok(shortLabelBranch.includes("whitespace-nowrap"), "it stays on one line at its full length");
  // Overflow is still handled by scrolling, never by shrinking.
  assert.ok(segmentedRow.includes("max-desk:overflow-x-auto"));
  assert.ok(/\[scrollbar-width:none\]|::-webkit-scrollbar/.test(segmentedRow), "no scrollbar chrome inside a pill");
});

test("the controls stay touch-sized and keep their active-state behaviour", () => {
  assert.ok(segmentedOption.includes("max-desk:min-h-9"), "a 36px+ target on a full-width pill");
  assert.ok(segmentedOption.includes("max-desk:px-3"), "the padding is unchanged");
  assert.ok(segmented.includes("aria-checked={isActive}"));
  assert.ok(segmented.includes("tabIndex={isActive ? 0 : -1}"));
  assert.ok(segmented.includes('role="radiogroup"'));
  assert.ok(segmented.includes('role="radio"'));
  assert.ok(segmented.includes('["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"]'));
  // The active pill is still scrolled back into view horizontally only.
  const effect = between(segmented, "useEffect(() => {\n    if (!mobileScroll) return;", "}, [value, mobileScroll]);");
  assert.ok(effect.includes("row.scrollLeft"));
  assert.ok(!effect.includes("scrollIntoView"));
  // One strip, one mounted view.
  assert.equal(count(source, /<SectionViewTabs\n {22}className="mb-4"/g), 1);
});

test("desktop keeps the exact strip it had", () => {
  // Every class this pass adds is max-tab: or max-desk:, so 1200px+ cannot
  // reach any of them, and the base declaration is byte-for-byte unchanged.
  assert.ok(
    segmented.includes(
      "inline-flex max-w-full items-center gap-1 rounded-full border border-[rgba(255,255,255,0.08)] bg-[rgba(15,23,42,0.58)] p-1"
    ),
    "the pill's own treatment is untouched"
  );
  assert.ok(segmented.includes('compact ? "px-2.5 py-1 text-[10px]" : "px-3 py-1.5 text-[11px] sm:px-4 sm:text-xs"'));
  assert.ok(segmented.includes('<span className="hidden whitespace-nowrap desk:block">{option?.label ?? optionValue}</span>'));
  for (const added of ["max-tab:grow", "max-desk:shrink-0", "max-tab:w-full", "max-tab:flex"]) {
    assert.ok(
      new RegExp(`(^|[\\s"\`])${added.replace(/[-:]/g, "\\$&")}`).test(segmented),
      `${added} is present`
    );
  }
  // Callers that never opted in are untouched.
  assert.ok(segmented.includes('<span className="block truncate">{option?.label ?? optionValue}</span>'));
  assert.ok(segmented.includes("mobileScroll = false"), "the whole treatment is still opt-in");
});

// ===========================================================================
// 2. The Simulation Results subtitle
// ===========================================================================

test("the subtitle is hidden below 1200px and still rendered at 1200px+", () => {
  const header = between(source, "<SectionEyebrow>03 · Raw evidence</SectionEyebrow>", "<SectionViewTabs");
  const subtitle = between(header, "The raw evidence", "</p>");
  const paragraph = header.slice(header.lastIndexOf("<p", header.indexOf("The raw evidence")), header.indexOf("</p>") + 4);

  assert.ok(subtitle.includes("full simulation outputs behind the score."), "the copy itself is not edited");
  assert.ok(paragraph.includes("max-desk:hidden"), "it is a visibility change, not a deletion");
  assert.ok(
    !/(?<!max-)desk:hidden/.test(paragraph),
    "an unqualified desk:hidden would remove it at 1200px+ too"
  );
  assert.ok(paragraph.includes("text-sm text-[var(--text-secondary)]"), "the desktop treatment is unchanged");
});

test("the heading and its info tooltip survive at every width", () => {
  const header = between(source, "<SectionEyebrow>03 · Raw evidence</SectionEyebrow>", "<SectionViewTabs");
  const heading = between(header, "<h2", "</h2>");
  assert.ok(heading.includes("Simulation Results"));
  assert.ok(!/max-desk:hidden|desk:hidden/.test(heading), "the title is never hidden");
  assert.ok(header.includes("<InfoPopover text={SIMULATION_RESULTS_INFO_TEXT} />"), "the tooltip stays");
  assert.ok(source.includes("const SIMULATION_RESULTS_INFO_TEXT ="));
});

// ===========================================================================
// 3. Outcome Distribution — the lower controls
// ===========================================================================

const markerChips = between(chart, "function MarkerChips(", "function ActiveMarkerLabel(");
const chipsRow = between(markerChips, '<div className="mt-4 flex flex-wrap', ">");
const chip = between(markerChips, "data-distribution-marker-chip", "</button>");

test("the dead space between the plot and the selectors collapses below desktop", () => {
  // A 20px aria-hidden spacer plus a 10px chip-row margin sat under the plot.
  const spacer = between(chart, '<div className="mt-1 min-h-[1rem]', "/>");
  assert.ok(spacer.includes("max-desk:mt-0"), "the spacer's margin collapses");
  assert.ok(spacer.includes("max-desk:min-h-0"), "and so does its reserved height");
  assert.ok(spacer.includes('aria-hidden="true"'), "it is still decorative on desktop");
  assert.ok(spacer.includes("mt-1 min-h-[1rem]"), "desktop keeps the breathing room");

  assert.ok(chipsRow.includes("max-desk:mt-2"), "the chip row sits closer to the plot");
  assert.ok(!chipsRow.includes("max-desk:mt-2.5"), "the previous, looser margin is gone");
  assert.ok(chipsRow.includes("mt-4"), "desktop keeps its 16px");
  // The plot itself also loses a little of the air above it.
  const plot = between(chart, 'ref={chartContainerRef} className="mt-4', ">");
  assert.ok(plot.includes("max-desk:mt-2"));
  assert.ok(plot.includes("h-[20rem]") && plot.includes("sm:h-[23rem]"), "the graph's own size is untouched");
});

test("phones lay the selectors out in two even columns instead of a ragged wrap", () => {
  assert.ok(chipsRow.includes("max-tab:grid"), "a grid below 600px");
  assert.ok(chipsRow.includes("max-tab:grid-cols-2"), "two columns, so the last row is never a lone chip");
  assert.ok(chipsRow.includes("max-desk:gap-1"), "tighter gutters below desktop");
  assert.ok(chipsRow.includes("flex flex-wrap"), "600-1199px still wraps as many per row as fit");
  assert.ok(chipsRow.includes("gap-2"), "desktop gutters are unchanged");
  assert.ok(chip.includes("max-desk:justify-center"), "a stretched chip centres its label");
});

test("the selectors are more compact but still touch-friendly", () => {
  assert.ok(chip.includes("max-desk:min-h-10"), "40px, down from 44px");
  assert.ok(!chip.includes("max-desk:min-h-11"));
  assert.ok(chip.includes("max-desk:h-auto"), "a long label may still grow the chip rather than clip");
  assert.ok(chip.includes("max-desk:px-2"), "slightly tighter horizontal padding");
  assert.ok(chip.includes("max-desk:text-[11px]"), "one step down, still legible");
  // Desktop's chip is untouched.
  assert.ok(chip.includes("inline-flex h-7 items-center rounded-full border px-3 text-xs"));
});

test("every marker option survives and still drives the chart", () => {
  // All eight configured markers reach the chip row: the component maps the
  // rows it already built, with no filter, slice or breakpoint-conditional set.
  const markers = between(source, "const chartMarkers = [", "\n  ];");
  for (const key of [
    "pack-cost",
    "median",
    "mean",
    "bad-floor",
    "big-hit",
    "big-hit-upside",
    "god-pull-upside",
    "max",
  ]) {
    assert.ok(markers.includes(`key: "${key}"`), `${key} must remain a marker`);
  }
  assert.equal(count(markers, /key: "/g), 8, "no marker was added or dropped");

  assert.ok(markerChips.includes("{markerRows.map((marker) => ("));
  assert.ok(!/markerRows[\s\S]{0,120}\.(?:slice|filter)\(/.test(code(markerChips)), "no option is dropped below desktop");
  assert.ok(!/isMobile|isBelowDesktop/.test(code(markerChips)), "the chip set is not branched on a JS breakpoint flag");
  // Selection behaviour is byte-for-byte what it was.
  assert.ok(chart.includes("onClick={() => onMarkerClick(marker.key)}"));
  assert.ok(chart.includes("setActiveMarkerKey((current) => (current === markerKey ? null : markerKey))"));
  assert.ok(markerChips.includes("aria-pressed={activeMarkerKey === marker.key}"));
  // The value is still reachable at every width.
  assert.ok(chart.includes("aria-label={`${marker.label}: ${formatCompactCurrency(marker.value)}`}"));
  assert.ok(chart.includes("title={`${marker.label}: ${formatCompactCurrency(marker.value)}`}"));
  assert.ok(markerChips.includes("data-distribution-active-readout"), "the one compact readout stays");
});

test("the graph itself is not redesigned by this pass", () => {
  // The approved axis simplification and its flag are exactly as the previous
  // pass left them — five reads, three mentions of the setter.
  assert.equal(count(chart, /isBelowDesktop/g), 5);
  assert.equal(count(chart, /setIsBelowDesktop/g), 3);
  assert.ok(chart.includes("<Tooltip content={<CombinedTooltip />}"), "tooltip interaction is untouched");
  assert.ok(chart.includes('yAxisId="right"\n                type="monotone"\n                dataKey="chance_to_reach_percent"'));
  const xAxis = between(chart, "<XAxis", "/>");
  assert.ok(xAxis.includes('dataKey="x_slot"'), "the bucket labels are untouched");
  assert.ok(!xAxis.includes("max-tab") && !xAxis.includes("max-desk"));
  assert.ok(chart.includes("Frequency Shape") && chart.includes("Chance To Reach"), "both series toggles remain");
});

// ===========================================================================
// 4. Simulation Drivers
// ===========================================================================

const driversList = between(source, "function SimulationDriversCompactList(", "function TopEVDriversContent(");
const driverDetail = between(driversList, "id={detailRegionId}", "\n      </div>");

test("the ranked list is unchanged: order, rank, name, share and value", () => {
  assert.ok(driversList.includes('data-simulation-drivers-compact className="min-w-0 desk:hidden"'));
  assert.ok(driversList.includes("const rows = hits.map((hit, index) => {"), "mapped in place");
  assert.ok(driversList.includes("rank: index + 1"));
  assert.ok(!driversList.includes("sort("), "ordering is the backend's");
  assert.ok(!/hits\.(?:filter|slice)\(/.test(driversList), "no driver is dropped");
  assert.ok(driversList.includes("grid-cols-[1.5rem_minmax(0,1fr)_4.5rem]"));
  assert.ok(driversList.includes("{row.rank}"));
  assert.ok(driversList.includes("{row.name}"));
  assert.ok(driversList.includes("{row.evShare} of pack value"), "the share still rides under the name");
  assert.ok(driversList.includes("{formatCurrency(row.ev)}"), "the value column survives");
  assert.ok(
    driversList.includes("ev !== null && totalEV !== null && totalEV > 0 ? `${((ev / totalEV) * 100).toFixed(1)}%` : null"),
    "the share expression is the desktop one"
  );
  // Selection and its highlight are untouched.
  assert.ok(driversList.includes("useState(0)"), "the highest driver is still selected by default");
  assert.ok(driversList.includes("COMPACT_ROW_SELECTED_CLASS"));
  assert.ok(driversList.includes("COMPACT_ROW_IDLE_CLASS"));
  assert.ok(driversList.includes("min-h-11"), "the rows keep their 44px target");
  assert.ok(driversList.includes("aria-expanded={isSelected}"));
  assert.ok(driversList.includes("aria-controls={detailRegionId}"));
});

test("the detail panel keeps Market Price and nothing the list already says", () => {
  assert.equal(count(code(driversList), /data-simulation-driver-detail/g), 1, "still one shared region");
  assert.ok(driverDetail.includes('aria-live="polite"'));
  assert.ok(driverDetail.includes("COMPACT_DETAIL_CLASS"), "the shared rail treatment survives");
  assert.ok(driverDetail.includes('label="Market Price"'), "the one field the list does not carry");
  assert.ok(driverDetail.includes("selected.nearMintPrice === null ? \"—\" : formatCurrency(selected.nearMintPrice)"));
  assert.ok(driverDetail.includes("{selected.name}"), "the panel still names what is selected");
});

test("the redundant detail rows, the thumbnail and the caveat are gone below desktop", () => {
  for (const removed of [
    'label="Value Contribution"',
    'label="Share of pack value"',
    "Price-based metrics use estimated third-party market snapshots and may change over time.",
    "<SimulationDriverThumbnail",
  ]) {
    assert.ok(!driversList.includes(removed), `${removed} must not remain in the compact list`);
  }
  assert.ok(!source.includes("function SimulationDriverThumbnail("), "its only caller is gone, so the component goes too");
  // The detail is now short enough to be described exhaustively.
  assert.equal(count(code(driverDetail), /<RipBreakdownDetailMetric/g), 1, "exactly one metric row");
  assert.ok(!/<img/.test(driverDetail), "no image in the mobile detail panel");
});

test("the desktop drivers tree still shows every field mobile drops", () => {
  const desktopCard = between(source, "function TopHitRow(", "function TopDriverListRow(");
  assert.ok(desktopCard.includes("Market Price"));
  assert.ok(desktopCard.includes("Value Contribution"));
  assert.ok(desktopCard.includes("{evShare} of pack value"));
  assert.ok(desktopCard.includes("TOP_CARD_IMAGE_CONTAINER_COMPACT_CLASS"), "the desktop card art survives");
  assert.ok(desktopCard.includes("<img"));
  assert.ok(
    source.includes('<div className="hidden min-w-0 gap-x-5 desk:grid lg:grid-cols-2">'),
    "and it is what 1200px+ renders"
  );
  assert.equal(
    count(source, /Price-based metrics use estimated third-party market snapshots and may change over time\./g),
    1,
    "the caveat survives once, on the desktop tree"
  );
});

test("the interpretation stays, with its badge, and only loses vertical air", () => {
  const intro = between(source, '<SimulationResultsPanel id="set-detail-simulation-drivers">', "<TopEVDriversContent");
  assert.ok(intro.includes("<InterpretationInsight"), "the interpretation still renders");
  assert.ok(intro.includes("sectionMeta={topEvDriversMeta}"), "from the same backend meta");
  assert.ok(intro.includes("Simulated Expected Value"), "the headline figure stays");
  assert.ok(!intro.includes("desk:hidden"), "no copy is removed below desktop");
  // Only size and spacing move, and only below 1200px.
  const insight = between(intro, "<InterpretationInsight", "/>");
  const insightClassName = insight.match(/className="([^"]*)"/);
  assert.ok(insightClassName, "the callout is styled by a plain class list");
  const insightClasses = insightClassName[1].split(/\s+/).filter(Boolean);
  assert.ok(insightClasses.includes("max-desk:py-0.5"), "the callout's own padding tightens");
  assert.ok(insightClasses.includes("max-desk:[&>p]:text-xs"), "and its body drops one type step");
  for (const className of insightClasses) {
    assert.ok(
      className === "min-w-0" || className.startsWith("max-desk:"),
      `${className} would restyle the callout at 1200px+ as well`
    );
  }
  // The badge — "TOP CARD LEADS VALUE" and friends — is untouched.
  const insightComponent = read("InterpretationInsight.jsx");
  assert.ok(insightComponent.includes("<InterpretationBadge label={label}"));
  assert.ok(insightComponent.includes('const bodyTextClass = compact ? "text-sm leading-snug" : "text-sm leading-relaxed";'),
    "the shared component's own defaults are untouched, so no other caller moves");
});

// ===========================================================================
// 5. Blast radius
// ===========================================================================

test("this pass touched no data path, no calculation and no dependency", () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(here, "../../package.json"), "utf8"));
  const deps = { ...pkg.dependencies, ...pkg.devDependencies };
  assert.ok(deps.recharts, "recharts is still the chart library");
  assert.ok(!deps["react-window"] && !deps["framer-motion"]);
  for (const tree of [code(driversList), code(markerChips)]) {
    assert.ok(!/\bfetch\(|axios|useSWR|getPokemonSet/.test(tree), "no request path");
  }
  // The sections this pass was told to leave alone keep their compact lists.
  assert.ok(source.includes("function SimulationMetricsCompactList("));
  assert.ok(source.includes("const PACK_PATH_DESKTOP_ONLY_EVIDENCE = new Set(["));
});

test("every class this pass adds is scoped below 1200px", () => {
  const added = [
    [segmented, ["max-tab:flex", "max-tab:w-full", "max-tab:grow", "max-desk:shrink-0"]],
    [chart, ["max-desk:mt-0", "max-desk:min-h-0", "max-tab:grid-cols-2", "max-desk:min-h-10", "max-desk:justify-center"]],
  ];
  for (const [file, classes] of added) {
    for (const className of classes) {
      assert.ok(file.includes(className), `${className} must be present`);
      assert.ok(/^max-(?:tab|desk):/.test(className), `${className} must be breakpoint-scoped`);
    }
  }
  // No new desk:hidden anywhere in the trees this pass edited — hiding desktop
  // content is never how a below-1200px pass expresses itself.
  assert.ok(!code(markerChips).includes("desk:hidden") || code(markerChips).includes("desk:hidden\">{marker.label}"),
    "the only desk:hidden in the chip is the pre-existing label/value swap");
  assert.ok(!code(segmentedRow).includes("desk:hidden"));
});
