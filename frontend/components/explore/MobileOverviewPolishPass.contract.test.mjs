import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

// Polish pass over the mobile/tablet Set Overview: gutters, chart edge
// clipping, a single date system, OPvC metric alignment, the Top Chase reveal
// affordance, Decision Signals density, and the pinned set-control block's
// opacity. Everything here is scoped below 1200px; the desktop assertions in
// each section exist to prove the 1200px+ composition was not touched.

const here = path.dirname(fileURLToPath(import.meta.url));
// RipStatisticsPageClient.jsx carries mixed CRLF/LF, so normalise before any
// multi-line anchor is searched for.
const read = (rel) => fs.readFileSync(path.resolve(here, rel), "utf8").replace(/\r\n/g, "\n");

const client = read("RipStatisticsPageClient.jsx");
const packValue = read("PackValueHistoryChart.jsx");
const edgeTick = read("ChartEdgeDateTick.jsx");
const rankBadge = read("../ui/RankBadge.jsx");
const scaffold = read("../Profile/PublicProfileLocalScaffold.js");
const css = read("../../app/styles/globals.css");

const mobileBlockStart = css.indexOf("@media (max-width: 1199.98px) {");
const mobileBlock = css.slice(mobileBlockStart, css.indexOf("\n}\n", mobileBlockStart));

const between = (source, startToken, endToken) => {
  const start = source.indexOf(startToken);
  assert.ok(start >= 0, `missing ${startToken}`);
  const end = source.indexOf(endToken, start);
  assert.ok(end > start, `missing ${endToken} after ${startToken}`);
  return source.slice(start, end);
};

const setValueChart = between(client, "function SetValueLineChart(", "function SetValueTrendCard(");
const setValueCard = between(client, "function SetValueTrendCard(", "function OverviewMetricTile(");
const chaseModule = between(client, "function TopChaseCardsModule(", "function hasMarketMoverRows(");
const chaseRow = between(client, "function TopMarketCardRow(", "function InlinePanelSkeleton(");
const compactSparkline = between(client, "function CompactSparkline(", "function normalizeSetValueHistoryPoints(");
const compactList = between(client, "function DecisionSignalsCompactList(", "function DecisionSignalRow(");
const openingEconomics = between(client, "data-overview-opening-economics", "</dl>");

// ===========================================================================
// 1. Width usage below 1200px
// ===========================================================================

test("the set page gutter is tightened without being removed", () => {
  const deskRecipe = scaffold.slice(scaffold.indexOf("  desk: {"), scaffold.indexOf("};", scaffold.indexOf("  desk: {")));
  assert.ok(deskRecipe.includes("px-3 pt-3 tab:px-4"), "12px phone / 16px tablet");
  assert.ok(!deskRecipe.includes("px-0 pt-3"), "a gutter still exists — content never bleeds to the edge");
  assert.ok(deskRecipe.includes("desk:px-0"), "desktop still hands the gutter to the content shell");
});

test("no section re-adds a horizontal inset inside the already-flush feed", () => {
  // The feed reset zeroes the card padding, so any px-* left on an inner row is
  // width taken from the data for no boundary.
  assert.ok(
    chaseRow.includes("px-3 py-2.5 max-desk:px-0 desk:"),
    "the Top Chase row is flush below desktop and padded on desktop"
  );
  assert.ok(openingEconomics.includes("px-0 py-1.5"), "the OPvC metric rows are flush below desktop");
  assert.ok(openingEconomics.includes("desk:px-3 desk:py-2"), "desktop keeps its column padding");
  assert.ok(compactList.includes("pl-1.5 pr-0"), "the Decision Signals rows reach the right edge");
});

test("the feed reset still zeroes the card padding it is responsible for", () => {
  assert.ok(mobileBlock.includes("padding-inline: 0;"));
  assert.ok(mobileBlock.includes("padding-block: 0;"));
});

// ===========================================================================
// 2. Chart clipping and one date system
// ===========================================================================

test("both charts inset their plot so the line caps are not clipped", () => {
  // An <svg> clips at its own viewport. With width={0} on the y-axis, a left
  // margin of 0 put the first point exactly on x=0 and cut its stroke — and all
  // of its glow — in half. The insets are now shared by both charts at every
  // width; see ChartResponsiveSizing for the full axis contract.
  const axis = read("minimalChartAxis.mjs");
  assert.ok(axis.includes("MINIMAL_PLOT_INSET_LEFT = 6"));
  assert.ok(axis.includes("MINIMAL_PLOT_INSET_RIGHT = 8"));
  for (const [name, source] of [["set value", setValueChart], ["opening profit vs cost", packValue]]) {
    assert.ok(source.includes("getMinimalPlotMargin("), `${name} must take the shared insets`);
  }
});

test("the two edge dates are anchored inward instead of centred on the clip edge", () => {
  for (const [name, source] of [["set value", setValueChart], ["opening profit vs cost", packValue]]) {
    assert.ok(
      source.includes("<ChartEdgeDateTick ticks={edgeDateTicks}"),
      `${name} must render the edge-anchored tick`
    );
  }
  assert.ok(edgeTick.includes('const textAnchor = isFirst ? "start" : isLast ? "end" : "middle";'));
  assert.ok(edgeTick.includes("edgeTicks.length > 1"), "a single-tick series still anchors from the left");
});

test("the redundant second date row is gone at every width", () => {
  // The chart's own axis prints the first and last date under the series, so the
  // bookend dates that used to sit either side of the Checklist/Hits/Top 10
  // selector stated the same two values a second time. They are now gone at
  // every size, not just below 1200px.
  assert.ok(!setValueCard.includes('|| "Start"'), "no start-date bookend survives");
  assert.ok(!setValueCard.includes('|| "Latest"'), "no end-date bookend survives");
  assert.ok(
    !/desk:grid-cols-\[minmax\(max-content,1fr\)_auto_minmax\(max-content,1fr\)\]/.test(setValueCard),
    "the three-column bookend row is gone"
  );
  assert.ok(setValueCard.includes("<SetValueScopeSelector"), "the selector itself is untouched");
});

test("the axis pass this builds on is not undone", () => {
  for (const [name, source] of [["set value", setValueChart], ["opening profit vs cost", packValue]]) {
    assert.ok(source.includes("edgeDateTicks"), `${name} still shows only first/last`);
    assert.ok(source.includes("MINIMAL_Y_AXIS_PROPS"), `${name} must keep the y-axis labels hidden`);
  }
  assert.ok(
    read("minimalChartAxis.mjs").includes("last && last !== first ? [first, last] : [first]"),
    "no intermediate x ticks may be reintroduced"
  );
  assert.ok(setValueChart.includes("<RechartsTooltip"), "Set Value keeps its tooltip");
  assert.ok(packValue.includes("<Tooltip"), "OPvC keeps its tooltip");
  assert.ok(setValueChart.includes('trigger={isCoarsePointer ? "click" : "hover"}'), "tap/scrub survives");
  assert.ok(packValue.includes('trigger={isCoarsePointer ? "click" : "hover"}'));
});

// ===========================================================================
// 3. Opening Profit vs Cost — metric alignment
// ===========================================================================

test("every OPvC value lands in the same right column", () => {
  // OpeningMetricTrendIndicator returns null when a metric has no trend, so with
  // the arrow trailing the number each row ended at a different x. Reversing the
  // pair below desktop puts the arrow inside and pins the value to the right
  // edge whether or not an arrow is present.
  assert.ok(openingEconomics.includes("grid-cols-[minmax(0,1fr)_auto]"), "label left, value right");
  assert.ok(openingEconomics.includes("justify-self-end"), "the value is right-aligned below desktop");
  assert.ok(
    openingEconomics.includes('className="inline-flex items-center gap-1.5 max-desk:flex-row-reverse"'),
    "the trend arrow sits inside the value below desktop"
  );
  assert.ok(openingEconomics.includes("desk:justify-self-auto"), "desktop keeps the stacked column layout");
});

test("the helper line hangs off the same right edge as the values", () => {
  assert.ok(
    openingEconomics.includes('className="col-span-2 text-[11px] font-normal leading-tight text-[var(--text-secondary)] max-desk:text-right desk:col-span-1"'),
    "the secondary line is right-aligned below desktop and unchanged on desktop"
  );
  assert.ok(openingEconomics.includes("headerExpectedLossText"), "the -$x.xx vs pack price line survives");
});

test("all three supporting metrics and their tooltips survive", () => {
  const metrics = between(client, "const headerDecisionMetrics = [", "];");
  for (const token of ["currentPackCost", "averagePackValue", "chanceToBeatPackCost"]) {
    assert.ok(metrics.includes(token), `${token} is still one of the three`);
  }
  assert.ok(openingEconomics.includes("<InfoPopover text={getMetricTooltip(metric.label)} />"), "info tooltips survive");
  assert.ok(openingEconomics.includes("<OpeningMetricTrendIndicator"), "trend indicators survive");
});

// ===========================================================================
// 4. Top Chase — reveal control
// ===========================================================================

test("the reveal control expands downward rather than pointing away", () => {
  assert.ok(!chaseModule.includes("→"), "no right-arrow affordance for a vertical expansion");
  assert.ok(chaseModule.includes('showAllChaseCards ? "Show less" : "Show more"'));
  assert.ok(chaseModule.includes("data-chase-reveal-chevron"));
  assert.ok(chaseModule.includes('${showAllChaseCards ? "rotate-180" : ""}'), "the chevron flips when expanded");
});

test("the reveal behaviour and the data behind it are unchanged", () => {
  assert.ok(chaseModule.includes("showAllChaseCards ? 10 : 5"), "5 by default, all 10 on reveal");
  assert.ok(chaseModule.includes("aria-expanded={showAllChaseCards}"));
  assert.ok(chaseModule.includes('aria-label={showAllChaseCards ? "Show fewer chase cards"'));
  assert.ok(chaseModule.includes("max-desk:min-h-11"), "the touch target survives");
  assert.ok(
    chaseModule.includes('`View all chase cards (${Math.min(totalRows, 10)})`'),
    "desktop wording is untouched"
  );
});

test("the Top Chase plot keeps its borderless, integrated look", () => {
  assert.ok(
    compactSparkline.includes("max-desk:rounded-none max-desk:border-0 max-desk:bg-transparent"),
    "the plot stays frameless below desktop"
  );
  assert.ok(
    compactSparkline.includes("rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/42"),
    "desktop keeps the frame"
  );
  assert.ok(chaseRow.includes("<CompactSparkline"), "scrubbing is still available per row");
});

// ===========================================================================
// 5. Decision Signals — compact polish
// ===========================================================================

test("a tier pill can never wrap onto two lines", () => {
  assert.equal(
    (rankBadge.match(/inline-flex items-center whitespace-nowrap rounded-full border/g) || []).length,
    2,
    "both the resolved and the unavailable badge refuse to wrap"
  );
  assert.ok(rankBadge.includes('format === "tier" && rank ? `${rank} Tier` : rank'), "the pill still reads `S Tier`");
});

test("the tier column is sized from the pill, not the pill squeezed into the column", () => {
  // `supporting` (px-3, 12px) needs ~62px for "S Tier" and was being handed a
  // 44px column, which is what broke "S" over "Tier".
  assert.ok(rankBadge.includes("compact: {"), "a dense size exists for fixed narrow columns");
  assert.ok(rankBadge.includes('className: "gap-1 px-2 py-0.5 text-[10px]"'));
  assert.ok(compactList.includes('size="compact"'), "the compact list uses it");
  assert.ok(!compactList.includes('size="supporting"'), "the oversized pill is gone from the compact list");
  const tierTrack = /grid-cols-\[minmax\(0,1fr\)_3rem_(3\.25rem)_2\.25rem\]/.exec(compactList);
  assert.ok(tierTrack, "the tier track is wider than the pill it holds");
});

test("the header and the rows share one column system", () => {
  assert.equal(
    (compactList.match(/grid-cols-\[minmax\(0,1fr\)_3rem_3\.25rem_2\.25rem\]/g) || []).length,
    2,
    "the column header and the row grid must not drift apart"
  );
  assert.equal((compactList.match(/gap-x-1\.5/g) || []).length, 2);
});

test("vertical bulk is reduced without losing the touch target", () => {
  assert.ok(compactList.includes("min-h-11"), "44px rows survive the compaction");
  assert.ok(compactList.includes("py-1 pl-1.5 pr-0"), "row padding is tightened");
  assert.ok(compactList.includes("pb-0.5 pt-2"), "group labels are tightened");
  assert.ok(
    compactList.includes('className="mt-2 min-h-[2.5rem] rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/45 px-2.5 py-1.5"'),
    "the shared detail region is compact"
  );
  for (const gone of ["py-1.5 pl-2 pr-1", "pb-1 pt-3", "min-h-[2.75rem]"]) {
    assert.ok(!compactList.includes(gone), `${gone} is superseded`);
  }
});

test("the scan structure, the values and the selection behaviour are untouched", () => {
  assert.ok(compactList.includes("{signal.label}"));
  assert.ok(compactList.includes('{signal.scoreText || "—"}'));
  assert.ok(compactList.includes("rank={signal.rankTier}"));
  assert.ok(compactList.includes("`#${rankLabel}`"));
  assert.ok(compactList.includes("toNumber(signal.rankValue)"), "ranks are still read straight off the view model");
  assert.ok(compactList.includes("Math.round(parsedRank)"));
  assert.ok(!/score\s*[*+/-]/.test(compactList), "no arithmetic is applied to any score");
  assert.ok(!compactList.includes("sort("), "row order is not re-sorted");
  assert.ok(compactList.includes("setSelectedLabel((previous) => (previous === signal.label ? null : signal.label))"));
  assert.ok(compactList.includes("selectedSignal.detailSummary || selectedSignal.summary"));
  assert.equal((compactList.match(/data-decision-signal-detail/g) || []).length, 1);
  assert.ok(compactList.includes("aria-expanded={isSelected}"));
  assert.ok(compactList.includes('aria-live="polite"'));
  assert.ok(compactList.includes("focus-visible:ring-2"));
  assert.ok(compactList.includes("border-l-[var(--accent)]"), "selection is not signalled by colour alone");
});

// ===========================================================================
// 6. The pinned set-control block is opaque
// ===========================================================================

test("nothing in the feed paints above the pinned set-control block", () => {
  const stickyZ = /\.set-detail-sticky-tabs \{[^}]*z-index: (\d+);/s.exec(mobileBlock);
  assert.ok(stickyZ, "the pinned block declares a z-index below desktop");
  const pinned = Number(stickyZ[1]);
  // .dashboard-container is `isolate`, so the sparkline and the pinned block
  // share one stacking context and are compared directly.
  const sparklineZ = /className=\{\["group relative z-(\d+) touch-pan-y/.exec(compactSparkline);
  assert.ok(sparklineZ, "the sparkline declares an explicit z-index");
  assert.ok(
    Number(sparklineZ[1]) < pinned,
    `the Top Chase sparkline (z-${sparklineZ[1]}) must stay under the pinned block (z-${pinned})`
  );
  const sparklineClassName = /className=\{\["group relative [^"]*"/.exec(compactSparkline);
  assert.ok(sparklineClassName, "the sparkline root className is where the stacking level is set");
  assert.ok(
    !sparklineClassName[0].includes("z-[60]"),
    "the value that painted over the pinned block is gone"
  );
});

test("the pinned block paints a solid surface below desktop", () => {
  const sticky = between(client, "className=\"set-detail-sticky-tabs", '"\n');
  assert.ok(sticky.includes("bg-[var(--surface-panel)]"), "fully opaque below desktop, not a 96% mix");
  assert.ok(
    sticky.includes("desk:bg-[color:color-mix(in_srgb,var(--surface-panel)_96%,transparent)]"),
    "the translucent mix is desktop-only"
  );
  assert.ok(sticky.includes("desk:backdrop-blur-md"), "the blur is desktop-only");
  assert.ok(
    !/(^|\s)backdrop-blur-md/.test(sticky),
    "no ungated blur may survive — it would apply below desktop too"
  );
});

test("the opacity gate lives where it can actually win", () => {
  // tailwind.config.js sets `important: true`, so EVERY utility is emitted
  // !important. A plain rule in globals.css can therefore never beat the
  // element's own background/backdrop utilities, whatever its specificity or
  // source order — the gate has to be a `desk:` variant on the element itself.
  const tailwindConfig = read("../../tailwind.config.js");
  assert.ok(/^\s*important:\s*true,/m.test(tailwindConfig), "the !important mode this depends on is still set");
  const stickyRule = mobileBlock.slice(
    mobileBlock.indexOf(".set-detail-sticky-tabs {"),
    mobileBlock.indexOf("}", mobileBlock.indexOf(".set-detail-sticky-tabs {"))
  );
  assert.ok(stickyRule.includes("position: sticky"), "the CSS rule still owns the pinning");
  assert.ok(stickyRule.includes("z-index: 40"), "and the stacking level");
  assert.ok(
    !stickyRule.includes("background:") && !stickyRule.includes("backdrop-filter:"),
    "the CSS must not carry a background/backdrop override that silently loses to a utility"
  );
});

test("the global navigation is not restyled to fix any of this", () => {
  assert.ok(read("../GlobalMobileBottomNav.js").includes("z-[60]"), "the global bottom nav is untouched");
  assert.ok(read("../StickyNav.js").includes("z-50"), "the global header is untouched");
  const stickyZ = /\.set-detail-sticky-tabs \{[^}]*z-index: (\d+);/s.exec(mobileBlock);
  assert.ok(Number(stickyZ[1]) < 50, "the set control block never competes with the global header");
});

// ===========================================================================
// Cross-cutting: desktop untouched, no new requests, no new dependencies
// ===========================================================================

test("the polish pass adds no dependency and no request path", () => {
  assert.ok(!edgeTick.includes("import "), "the new tick component pulls in nothing at all");
  for (const source of [client, packValue, edgeTick]) {
    assert.ok(!source.includes("require("), "no runtime require is introduced");
  }
  for (const [fetcher, expected] of [
    ["getPokemonSetOverview(", 1],
    ["getPokemonSetTopChase(", 1],
    ["getPokemonSetMarketMovers(", 1],
  ]) {
    assert.equal(
      (client.match(new RegExp(fetcher.replace(/[()]/g, "\\$&"), "g")) || []).length,
      expected,
      `${fetcher} must still have exactly ${expected} call site`
    );
  }
});

test("the pass introduces no duplicate chart mounts", () => {
  assert.equal((packValue.match(/<ResponsiveContainer/g) || []).length, 1);
  assert.equal((setValueChart.match(/<ResponsiveContainer/g) || []).length, 1);
  assert.equal((client.match(/<CompactSparkline/g) || []).length, 1);
});

test("every change below 1200px is gated so desktop composition is unchanged", () => {
  // Each edit either sits behind max-desk:/desk:, behind isDesktopComposition,
  // or inside the max-width media block.
  // Set Value no longer reads a width at all — its axis treatment is shared.
  // OPvC still does, only for its desktop inline end-of-series labels.
  assert.ok(!setValueChart.includes("useMediaQuery"), "Set Value has no width branch left");
  assert.ok(packValue.includes('useMediaQuery("(min-width: 1200px)", true)'), "desktop is the SSR default");
  assert.ok(client.includes("h-[16rem] w-full tab:h-[20rem] desk:h-[21rem]"), "chart sizing is unchanged");
  assert.ok(
    client.includes("relative min-h-[88px] overflow-visible rounded-t-xl border max-desk:hidden desk:order-1"),
    "the desktop context header keeps its composition"
  );
  assert.ok(client.includes('<div data-set-sticky-picker className="desk:hidden">'), "the sticky picker row is mobile-only");
  assert.ok(
    between(client, "function DecisionSignalsCard(", "// A Profit / Safety / Stability card.").includes(
      '<div className="hidden desk:block">'
    ),
    "the desktop Decision Signals tree is still the 1200px+ presentation"
  );
});
