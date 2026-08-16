// Set Value Rankings compact-row composition contract.
//
// The mobile ranking row is required to use TopMarketCardRow's responsive
// composition rather than a narrowed copy of the desktop ladder table. The
// regression this file exists to prevent: the mobile row adapted the desktop
// grid, which forced the sparkline into `width: min(10rem, 42vw)` — a fraction
// of the card — and split the information line away from its navigation region.
//
// Modelled on TopChaseCompactRows.contract.test.mjs, which guards the same
// composition for Top Chase Cards.

import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
// Mixed CRLF/LF in this checkout — normalize before any multi-line anchor.
const read = (name) => fs.readFileSync(path.resolve(here, name), "utf8").replace(/\r\n/g, "\n");

const source = read("ExploreTopRankings.jsx");
const css = read("explore.module.css");
const sparkline = read("MarketSparkline.jsx");

const row = source.slice(source.indexOf("return <li key={target.setId}"), source.indexOf("</div></li>;"));
const navStart = row.indexOf("<Link data-ranking-nav");
const navEnd = row.indexOf("</Link>");
const mobileBlock = css.slice(css.indexOf("@media (max-width: 1199.98px)"));

test("1. the mobile information row carries rank, logo, identity and value/change", () => {
  const nav = row.slice(navStart, navEnd);
  assert.ok(nav.includes("#{position}"), "rank");
  assert.ok(nav.includes("<SetLogo"), "set logo");
  assert.ok(nav.includes("{name}") && nav.includes("target?.era"), "set name and era");
  assert.ok(nav.includes('data-ranking-value="compact"'), "value and change");

  // Four regions on one compact line: rank | logo | identity | value.
  assert.ok(
    mobileBlock.includes("grid-template-columns: 1.75rem 2.25rem minmax(0, 1fr) auto;"),
    "the compact line is a four-column grid in the Top Chase shape"
  );
});

test("2. the chart is a sibling that follows the navigation region", () => {
  assert.ok(navStart >= 0 && navEnd > navStart, "the navigation region must be locatable");
  assert.ok(row.indexOf("data-ranking-chart") > navEnd, "the chart renders after the link closes");
  assert.ok(row.includes("data-ranking-nav"), "the navigation region is identifiable");
  assert.ok(row.includes("data-ranking-chart"), "the chart region is identifiable");
});

test("3. the chart is never nested inside an anchor", () => {
  assert.ok(!row.slice(navStart, navEnd).includes("<Sparkline"), "not inside the identity link");
  const valueNavStart = row.indexOf("<Link data-ranking-value-nav");
  assert.ok(valueNavStart > row.indexOf("data-ranking-chart"), "the value link opens after the chart closes");
  assert.ok(!row.slice(valueNavStart).includes("<Sparkline"), "not inside the value link");
});

test("4. the mobile chart is full width", () => {
  assert.ok(
    mobileBlock.includes(".ladderRow > [data-ranking-chart] {\n    grid-column: 1 / -1;\n    grid-row: 2;\n    width: 100%;\n  }"),
    "the trend band spans the row and takes its full content width"
  );
  assert.ok(source.includes('className="w-full"'), "the sparkline wrapper fills its cell");
});

test("5. no fixed or viewport-relative cap constrains the mobile chart", () => {
  assert.ok(!css.includes("min(10rem, 42vw)"), "the 42vw cap is gone");
  assert.ok(!/\[data-ranking-chart\][^}]*max-width/.test(css), "no max-width on the chart cell");
  assert.ok(!source.includes("max-w-["), "no Tailwind max-width on the rankings sparkline");
});

test("6. value and change are part of the mobile navigation region", () => {
  const nav = row.slice(navStart, navEnd);
  assert.ok(nav.includes('data-ranking-value="compact"'), "the compact value renders inside the link");
  assert.ok(nav.includes("desk:hidden"), "the compact value is below-desktop only");
  // Desktop moves it out to its own sibling link rather than nesting the chart.
  assert.ok(row.includes('data-ranking-value="table"'), "the desktop value cell is identifiable");
  assert.ok(mobileBlock.includes(".ladderValueNav { display: none; }"), "the column-four link is desktop only");

  // Computed once, rendered per composition — TopMarketCardRow's priceCell rule.
  assert.equal((source.match(/const valueCell = /g) || []).length, 1, "one value cell definition");
  assert.equal((row.match(/\{valueCell\}/g) || []).length, 2, "rendered in exactly the two compositions");
});

test("7. desktop is still Rank | Set | Trend | Set value / change", () => {
  assert.ok(
    css.includes("grid-template-columns: 2.25rem minmax(9rem, 1.35fr) minmax(7rem, 1fr) minmax(8.5rem, auto);"),
    "the desktop four-column template is unchanged"
  );
  assert.ok(css.includes(".ladderNav {\n  display: grid;\n  grid-column: 1 / 3;"), "the link owns columns one and two");
  assert.ok(css.includes(".ladderRow > [data-ranking-chart] {\n  grid-column: 3;\n  grid-row: 1;\n}"), "the trend is column three");
  assert.ok(css.includes(".ladderValueNav {\n  display: block;\n  grid-column: 4;"), "the value is column four");
  for (const label of ["Rank", "Set", "Trend", "Set value / change"]) {
    assert.ok(source.includes(label), `the ${label} header survives`);
  }
  // Reading order matches visual order: trend before value.
  assert.ok(row.indexOf("data-ranking-chart") < row.indexOf("data-ranking-value-nav"));
});

test("8. the latest tooltip delta is the selected-window delta, not a daily step", () => {
  // Both numbers resolve from the SAME published movement through one helper,
  // so the tooltip's latest point cannot disagree with the row's chip.
  assert.ok(source.includes("baselineValue={resolveDeltaWindowBaselineValue(movement, value)}"));
  assert.ok(source.includes("movement?.amount") && source.includes("movement?.percent"));
  assert.ok(sparkline.includes("computeChangeFromBaseline"), "the sparkline reuses the canonical helper");

  // Per-consumer semantics: the baseline mode is opt-in, so Top Chase keeps its
  // point-over-point reading rather than being changed globally.
  assert.ok(sparkline.includes("baselineValue = null"), "baseline mode defaults off");
  assert.ok(sparkline.includes("activePoint.y - previousPoint.y"), "the point-over-point path survives for callers without a window");
  assert.ok(!read("RipStatisticsPageClient.jsx").includes("baselineValue="), "Top Chase is untouched");
});

test("9. nothing is repaired with stopPropagation", () => {
  assert.ok(!/\.stopPropagation\s*\(/.test(source), "sibling composition removes any need to cancel propagation");
  // Nor with a stretched overlay standing in for real link content.
  assert.ok(!css.includes(".ladderNav {\n  position: absolute;"), "the navigation region is not an empty overlay");
});

test("10. the market snapshot and performance architecture is untouched", () => {
  assert.ok(!source.includes("fetch("), "no per-row request");
  assert.ok(!source.includes("useEffect"), "no added effects");
  assert.ok(source.includes("target?.currentSetValue"), "values still come from the published snapshot");
  assert.ok(source.includes("target?.windows?.[selectedWindowKey]"), "movements still come from the published snapshot");
  assert.ok(source.includes("target?.trend"), "the trend still comes from the published snapshot");
  assert.ok(source.includes("useMemo(() => buildRows(targets, selectedWindowKey)"), "row projection stays memoized");
});
