import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (relativePath) =>
  fs.readFileSync(path.resolve(here, relativePath), "utf8").replace(/\r\n/g, "\n");

const client = read("RipStatisticsPageClient.jsx");
const packValue = read("PackValueHistoryChart.jsx");
const axis = read("minimalChartAxis.mjs");

const setValueChart = client.slice(
  client.indexOf("function SetValueLineChart("),
  client.indexOf("function SetValueTrendCard(")
);

test("Set Value Trend sizes to phone, tablet and desktop", () => {
  // Phone 16rem = 256px (brief: 240-280). Tablet 20rem = 320px (brief: 300-340).
  // Desktop keeps its existing 21rem.
  assert.ok(setValueChart.includes("h-[16rem] w-full tab:h-[20rem] desk:h-[21rem]"));
  assert.ok(setValueChart.includes("min-h-[16rem] w-full tab:min-h-[20rem] desk:min-h-[21rem]"));
  assert.ok(!/ChartFrame className="h-\[21rem\] w-full"/.test(setValueChart), "the flat desktop height is gone");
});

test("Opening Profit vs Cost matches that sizing grammar", () => {
  assert.ok(packValue.includes("min-h-[17rem] w-full flex-1 tab:min-h-[21rem] desk:min-h-[24rem]"));
  assert.ok(packValue.includes("min-h-[19rem] flex-col tab:min-h-[23rem] desk:min-h-[26rem]"));
});

// ---------------------------------------------------------------------------
// The minimal axis is now the SHARED treatment at every width.
//
// Superseding the earlier "below 1200px only" rule: the y-axis tick labels and
// the intermediate x-axis dates are gone at every size, and both charts read
// their axis configuration from one module so Overview and Insights cannot
// drift apart. The scales themselves are untouched — each chart still computes
// and passes its own domain — and exact values stay reachable by hover and by
// tap/scrub.
// ---------------------------------------------------------------------------

test("both charts take their axis treatment from one shared module", () => {
  for (const [name, source] of [["set value", setValueChart], ["opening profit vs cost", packValue]]) {
    assert.ok(source.includes("MINIMAL_Y_AXIS_PROPS"), `${name} must use the shared y-axis props`);
    assert.ok(source.includes("buildEdgeDateTicks("), `${name} must use the shared edge-date builder`);
    assert.ok(source.includes("getMinimalPlotMargin("), `${name} must use the shared plot margin`);
  }
  assert.ok(packValue.includes('from "@/components/explore/minimalChartAxis.mjs"'));
  assert.ok(client.includes('from "@/components/explore/minimalChartAxis.mjs"'));
});

test("the shared module hides the y-axis labels and reserves no gutter", () => {
  assert.ok(axis.includes("tick: false"), "no printed y tick labels");
  assert.ok(axis.includes("width: 0"), "no reserved y gutter");
  assert.ok(axis.includes("MINIMAL_PLOT_INSET_LEFT = 6"));
  assert.ok(axis.includes("MINIMAL_PLOT_INSET_RIGHT = 8"));
});

test("neither chart reintroduces a y-axis label at any width", () => {
  for (const [name, source] of [["set value", setValueChart], ["opening profit vs cost", packValue]]) {
    assert.ok(
      !/tick=\{isDesktopComposition \? \{ fill/.test(source),
      `${name} must not gate the y tick labels back on for desktop`
    );
    assert.ok(!/width=\{isDesktopComposition \? \d+ : 0\}/.test(source), `${name} must not restore the desktop y gutter`);
  }
});

test("the x-axis carries only the first and last date, at every width", () => {
  for (const [name, source] of [["set value", setValueChart], ["opening profit vs cost", packValue]]) {
    assert.ok(source.includes("ticks={edgeDateTicks}"), `${name} must place exactly the edge ticks`);
    assert.ok(source.includes("interval={0}"), `${name} must not let Recharts drop or add ticks`);
    assert.ok(
      source.includes("<ChartEdgeDateTick ticks={edgeDateTicks}"),
      `${name} must anchor the two edge dates inward so they cannot be clipped`
    );
    assert.ok(!source.includes('"preserveStartEnd"'), `${name} must not keep the old desktop spacing mode`);
    assert.ok(!source.includes("mobileEdgeDateTicks"), `${name} must not keep a mobile-only tick path`);
  }
  assert.ok(
    axis.includes("last && last !== first ? [first, last] : [first]"),
    "one date when the series has a single point, two otherwise"
  );
});

test("Set Value no longer needs a width branch at all", () => {
  assert.ok(
    !setValueChart.includes("isDesktopComposition"),
    "with one shared axis treatment there is no desktop composition left to read"
  );
  assert.ok(setValueChart.includes("usePointerMode()"), "pointer capability is still read — it is not a width");
});

test("Opening Profit vs Cost keeps its desktop inline end labels and their margin", () => {
  // These are the desktop presentation of the same three latest values the
  // compact row carries below 1200px — series annotations, not axis labels — so
  // the axis unification does not remove them.
  assert.ok(packValue.includes('useMediaQuery("(min-width: 1200px)", true)'), "still seeded for SSR");
  assert.equal(
    (packValue.match(/index === latestDataIndex && isDesktopComposition/g) || []).length,
    3,
    "all three inline labels remain desktop-only"
  );
  assert.ok(
    packValue.includes("rightExtra: isDesktopComposition ? 104 : 0"),
    "the extra right margin is added to the shared inset, not substituted for it"
  );
});

test("the three series values survive when the inline end labels do not", () => {
  // Expected Value / Typical Return / Realistic Upside are relocated, never
  // removed: below 1200px they render in a compact row under the legend.
  assert.ok(packValue.includes("data-latest-values"), "a latest-values row exists below desktop");
  assert.ok(
    !/index === latestDataIndex(?! &&)/.test(packValue),
    "no inline label may stay ungated"
  );
  for (const token of ["seriesLabels.mean", "seriesLabels.median", "seriesLabels.p95"]) {
    const row = packValue.slice(packValue.indexOf("data-latest-values"), packValue.indexOf("</dl>"));
    assert.ok(row.includes(token), `${token} must appear in the latest-values row`);
  }
});

test("timeframe controls scroll rather than shrink to unreadable text", () => {
  assert.ok(client.includes("max-desk:overflow-x-auto max-desk:flex-nowrap"));
  assert.ok(!setValueChart.includes("text-[9px]"), "controls must not be shrunk into illegibility");
});

test("the Set Value card stops reserving desktop height on a phone", () => {
  assert.ok(client.includes('className="flex min-h-0 flex-col space-y-4 desk:min-h-[29rem]"'));
});
