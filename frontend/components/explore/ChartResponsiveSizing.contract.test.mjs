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

test("mobile drops the y-axis labels and gives the plot the full page width", () => {
  // Superseding the earlier "reduce density but keep a 44px gutter" rule: below
  // 1200px the vertical tick labels are removed entirely and the axis reserves
  // no width, so the series spans the page. The scale itself is untouched
  // (domain/ticks are unchanged) and exact values stay reachable by tap/scrub.
  for (const [name, source, desktopWidth] of [
    ["set value", setValueChart, "58"],
    ["opening profit vs cost", packValue, "60"],
  ]) {
    assert.ok(source.includes("const isDesktopComposition = useMediaQuery"), `${name} must read the desktop composition`);
    assert.ok(
      source.includes('tick={isDesktopComposition ? { fill: "var(--text-secondary)", fontSize: 11 } : false}'),
      `${name} must hide y-axis tick labels below desktop`
    );
    assert.ok(
      source.includes(`width={isDesktopComposition ? ${desktopWidth} : 0}`),
      `${name} must reserve no y-axis gutter below desktop, and keep ${desktopWidth}px on desktop`
    );
  }
  // Desktop scale behaviour is unchanged.
  assert.ok(setValueChart.includes("tickCount={isDesktopComposition ? undefined : 4}"));
  assert.ok(setValueChart.includes("ticks={isDesktopComposition ? yAxisTicks : undefined}"));
});

test("mobile x-axis shows only the first and last date", () => {
  for (const [name, source] of [
    ["set value", setValueChart],
    ["opening profit vs cost", packValue],
  ]) {
    assert.ok(
      source.includes("mobileEdgeDateTicks"),
      `${name} must compute a first/last-only tick set below desktop`
    );
    assert.ok(
      /isDesktopComposition \|\| (chartData|numericPoints)\.length === 0/.test(source),
      `${name} must leave desktop ticks untouched`
    );
    assert.ok(
      source.includes('last && last !== first ? [first, last] : [first]'),
      `${name} must emit exactly the first and last date (or one, when they coincide)`
    );
  }
  // Desktop keeps preserveStartEnd spacing.
  assert.ok(packValue.includes('interval: "preserveStartEnd"'));
  assert.ok(setValueChart.includes('"preserveStartEnd"'));
});

test("the desktop composition defaults to true so desktop never flashes mobile", () => {
  for (const [name, source] of [["set value", setValueChart], ["opening profit vs cost", packValue]]) {
    assert.ok(
      source.includes('useMediaQuery("(min-width: 1200px)", true)'),
      `${name} must seed the desktop answer for SSR and first paint`
    );
  }
});

test("the wide desktop right margin does not eat the phone plot", () => {
  assert.ok(packValue.includes("right: isDesktopComposition ? 112 : 12"));
});

test("the three series values survive when the inline end labels do not", () => {
  // Expected Value / Typical Return / Realistic Upside are relocated, never
  // removed: below 1200px they render in a compact row under the legend.
  assert.ok(packValue.includes("data-latest-values"), "a latest-values row exists below desktop");
  assert.equal(
    (packValue.match(/index === latestDataIndex && isDesktopComposition/g) || []).length,
    3,
    "all three inline labels are desktop-only"
  );
  assert.ok(
    !/index === latestDataIndex(?! &&)/.test(packValue),
    "no inline label may stay ungated"
  );
  // The relocated row carries the same three series, with the same colours.
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
