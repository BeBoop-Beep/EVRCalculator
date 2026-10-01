import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./FinancialRipHistoryChart.jsx", import.meta.url), "utf8");
const model = readFileSync(new URL("./financialRipHistoryModel.mjs", import.meta.url), "utf8");
const legend = readFileSync(new URL("./FinancialRipHistoryLegend.jsx", import.meta.url), "utf8");
const tooltipSource = readFileSync(new URL("./FinancialRipHistoryTooltip.jsx", import.meta.url), "utf8");
const distribution = readFileSync(new URL("./OpeningEconomicsDistribution.jsx", import.meta.url), "utf8");

test("uses the Financial RIP history reader and no legacy benchmark reader", () => {
  assert.ok(source.includes("readFinancialHistoryCached"));
  assert.ok(!source.includes("readBenchmarkHistory"));
  assert.ok(source.indexOf("shouldFetchFinancialRipHistory") < source.indexOf("readFinancialHistoryCached(requestEntities"));
  assert.match(source, /financialRipRequestEntities\(\s*selected,\s*request\.view\?\.mode === mode \? request\.view\?\.selected : \[\],\s*seededModes\[mode\] \? candidates : \[\],?\s*\)/);
});

test("locked access is a synthetic frosted preview with no chart data dependency", () => {
  assert.ok(source.includes("data-financial-rip-history-locked"));
  assert.ok(source.includes("backdrop-blur-md"));
  assert.ok(source.includes("INDEX_PLAN_PLUS"));
  assert.ok(source.includes("<LockedPreview />"));
});

test("controls, observed-date continuity, moving reference, and responsive frame are explicit", () => {
  for (const label of ["Sets", "Eras", "Overall Financial RIP"]) assert.ok(source.includes(label));
  for (const window of ["1D", "7D", "30D", "3M", "6M", "1Y", "ALL"]) assert.ok(model.includes(`key: "${window}"`));
  assert.equal((source.match(/connectNulls/g) || []).length, 2);
  assert.ok(source.includes("<ChartFrame"));
  assert.ok(source.includes("h-[20rem] sm:h-[24rem] desk:h-[28rem]"));
  assert.ok(source.includes("MultiSelectFilter"));
  assert.ok(source.includes('mode === "sets" ? "Sets…" : "Eras…"'));
  assert.ok(source.includes('searchPlaceholder="Search Eras…"'));
  assert.ok(source.includes("setIdsForEra"));
  assert.ok(source.includes('stroke="#ffffff"'));
  assert.ok(source.includes('strokeDasharray="9 7"'));
  assert.ok(source.includes("strokeWidth={3}"));
  assert.ok(source.includes("strokeOpacity={0.9}"));
  assert.equal((source.match(/connectNulls=\{false\}/g) || []).length, 2);
});

test("selector chips are absent and one complete removable legend preserves permanent Overall", () => {
  assert.equal((source.match(/showChips=\{false\}/g) || []).length, 2);
  assert.doesNotMatch(source, /chart\.series\.slice\(0, 5\)|selected Sets/);
  assert.match(legend, /series\.map\(\(item\).*Remove \$\{item\.name\} from Financial RIP chart/s);
  assert.doesNotMatch(source, /Choose at least one .* to view Financial RIP history/);
  assert.match(legend, /flex flex-wrap/);
  assert.match(source, /<FinancialRipHistoryLegend/);
});

test("Era preset bypasses only the manual five cap and removals are local", () => {
  assert.match(source, /presetEraId \? current : current\.slice\(0, MAX_FINANCIAL_RIP_SET_SELECTION\)/);
  assert.match(source, /setSetSelection\(ids\)/);
  assert.match(source, /setSetSelection\(\(current\) => current\.filter/);
  assert.match(source, /selected\.every\(\(item\) => loadedIds\.has/);
});

test("compact tooltip uses one Overall, dynamic ordering helper, and no rank or cohort", () => {
  const tooltip = tooltipSource;
  assert.match(tooltip, /financialRipTooltipRows/);
  assert.equal((tooltip.match(/>Overall<\/span>/g) || []).length, 1);
  assert.doesNotMatch(tooltip, /Rank|cohort|Financial RIP <strong>/);
  assert.match(tooltip, /backgroundColor: row\.color/);
});

test("refresh and failure preserve the last successful certified chart", () => {
  assert.match(source, /setRequest\(\(current\) => \(\{\s*\.\.\.current,\s*status: "loading"/);
  assert.ok(source.includes("request.view?.mode === mode ? request.view : null"));
  assert.ok(source.includes("The latest refresh failed, so the last successful history remains visible."));
  assert.ok(legend.includes("Updating history"));
});

test("the retired Financial Return chart cannot return as a second authority", () => {
  const retiredName = `./${"Financial"}${"Return"}${"History"}.jsx`;
  const retiredSymbol = `${"Financial"}${"Return"}${"History"}`;
  assert.equal(existsSync(new URL(retiredName, import.meta.url)), false);
  assert.ok(distribution.includes('import FinancialRipHistoryChart from "./FinancialRipHistoryChart"'));
  assert.ok(!distribution.includes(retiredSymbol));
});

test("chart copy is valid UTF-8 and uses the canonical Rankings upgrade source", () => {
  for (const expected of ["Pok\u00e9mon-wide", "Loading Financial RIP history\u2026", " \u00b7 History available from"]) {
    assert.ok(source.includes(expected), `missing intended copy: ${expected}`);
  }
  assert.ok(source.includes('source="rankings"'));
  const brokenCopy = [
    `Pok${"\u00c3\u0192\u00c2\u00a9"}mon`,
    `Pok${"\u00c3\u00a9"}mon`,
    `${"\u00c3\u00a2"}${"\u00e2\u201a\u00ac\u00c2\u00a6"}`,
    `${"\u00e2"}${"\u20ac\u00a6"}`,
    `${"\u00c3\u201a"}${"\u00c2\u00b7"}`,
    `${"\u00c2"}\u00b7 History available from`,
  ];
  for (const broken of brokenCopy) assert.ok(!source.includes(broken), `found mojibake: ${broken}`);
});
