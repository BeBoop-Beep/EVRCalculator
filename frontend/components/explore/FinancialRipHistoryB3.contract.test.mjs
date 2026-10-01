import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const chart = read("./FinancialRipHistoryChart.jsx");
const legend = read("./FinancialRipHistoryLegend.jsx");
const lazy = read("./RankingsLazyClient.jsx");
const overall = read("./OpeningEconomicsOverall.jsx");
const distribution = read("./OpeningEconomicsDistribution.jsx");
const cache = read("../../lib/rankings/financialHistoryCache.mjs");
const fn = (source, startMarker, endMarker) => source.slice(source.indexOf(startMarker), source.indexOf(endMarker, source.indexOf(startMarker)));

test("Clear All empties the user selection only: no request, no re-seeding, no preset resurrection", () => {
  const clearAll = fn(chart, "const clearAll = useCallback", "const pinFromChart");
  assert.match(clearAll, /setSetSelection\(\[\]\)/);
  assert.match(clearAll, /setEraSelection\(\[\]\)/);
  assert.match(clearAll, /setPresetEraId\(null\)/);
  assert.doesNotMatch(clearAll, /readFinancialHistoryCached|peekFinancialHistory|setRequest|fetch\(/);
  assert.match(chart, /seeded\.current\.sets = true/);
  assert.match(chart, /if \(!seeded\.current\.sets\)/);
  // defaults only come from the one-time seed - never from "selection is empty"
  assert.doesNotMatch(chart, /current\.length \? .*: setCandidates\.slice\(0, 3\)/);
});

test("transport anchor is request-only: never part of the plotted series or legend", () => {
  assert.match(chart, /financialRipRequestEntities\(selected, .*seededModes\[mode\] \? candidates : \[\]\)/);
  assert.match(chart, /setSeededModes\(\(current\) => \(\{ \.\.\.current, sets: true \}\)\)/);
  assert.match(chart, /buildFinancialRipChartModel\(display\?\.payload\?\.rows \|\| \[\], selected,/);
  assert.match(chart, /<FinancialRipHistoryLegend\s+series=\{chart\.series\}/);
});

test("focus is display-only: it never touches selection or issues a request", () => {
  for (const handler of [fn(chart, "onToggleFocus=", "onHoverFocus="), fn(chart, "onHoverFocus=", "onRemove=")]) {
    assert.doesNotMatch(handler, /setSetSelection|setEraSelection|setRequest|readFinancialHistoryCached/);
  }
  assert.match(chart, /resolveActiveFocus\(\{ persistentId: focusId, hoverId, seriesIds \}\)/);
  assert.match(chart, /setFocusId\(\(current\) => \(current === id \? null : current\)\)/, "removing the focused entity clears focus");
  assert.match(chart, /if \(focusId != null && !seriesIds\.includes\(focusId\)\) setFocusId\(null\)/);
  assert.match(chart, /strokeOpacity=\{emphasis\.strokeOpacity\}/);
  assert.match(chart, /<Tooltip content=\{<ChartTooltip series=\{chart\.series\} focusId=\{activeFocus\}/);
  assert.match(legend, /event\.pointerType === "mouse"/);
});

test("Overall is never removable or hidden by focus", () => {
  assert.match(chart, /<Line type="linear" dataKey="overallFinancialRip"/);
  assert.doesNotMatch(chart.slice(chart.indexOf('dataKey="overallFinancialRip"'), chart.indexOf("{drawSeries.map")), /emphasis|strokeOpacity=\{emphasis/);
  assert.doesNotMatch(legend.slice(legend.indexOf("data-legend-overall"), legend.indexOf("{series.map")), /<button|onClick/);
});

test("tooltip: wheel is forwarded to the scroll region only, page scroll preserved at the limits", () => {
  const wheel = fn(chart, "const onWheel", "node.addEventListener");
  assert.match(chart, /addEventListener\("wheel", onWheel, \{ passive: false \}\)/);
  assert.match(wheel, /closest\?\.\(`\[\$\{TOOLTIP_SCROLL_ATTR\}\]`\)\) return/);
  assert.match(wheel, /region\.scrollHeight <= region\.clientHeight \+ 1\) return/);
  assert.match(wheel, /if \(atTop \|\| atBottom\) return/);
  assert.match(wheel, /event\.preventDefault\(\)/);
  assert.doesNotMatch(wheel, /setFocusId|setSetSelection|setRequest|setPinnedDate/);
  assert.doesNotMatch(chart, /pointer-events-none[^"]*recharts-wrapper|pointerEvents: ?"none"[^;]*chart/);
});

test("session cache plumbing: LazyClient -> OpeningEconomicsOverall -> Distribution -> chart, keyed by identity", () => {
  assert.match(lazy, /<OpeningEconomicsOverall [^>]*sessionCache=\{sessionCache\}/);
  assert.match(overall, /sessionCache = null/);
  assert.match(overall, /sessionCache=\{sessionCache\}/);
  assert.match(distribution, /<FinancialRipHistoryChart key=\{sessionCache\?\.identity \|\| "no-session"\} sessionCache=\{sessionCache\}/);
  assert.match(lazy, /createRankingsSessionCache\(`\$\{requestKey\}:\$\{publicationIdentity\}`\)/);
  assert.doesNotMatch(chart, /readFinancialRipHistory\(/);
  assert.doesNotMatch(cache, /globalThis|window\.|localStorage|sessionStorage|new Map\(\);\s*export/);
});

test("default prewarm and optional idle prefetch are parent-owned and gated", () => {
  const effect = fn(lazy, "const historyMarketDate", "const changeLens");
  assert.match(effect, /lens !== "overall" \|\| !canViewRankingsIntelligence/);
  assert.match(effect, /authStatus === "resolved" \|\| authStatus === "degraded"/);
  assert.match(effect, /defaultFinancialHistoryRequest\(\{ financialCohort, marketDate: historyMarketDate \}\)/);
  assert.match(effect, /prewarmFinancialHistory\(plan, \{ sessionCache, entitled: canViewRankingsIntelligence, authStatus \}\)/);
  assert.match(effect, /navigator\.connection\?\.saveData/);
  assert.match(effect, /requestIdleCallback/);
  assert.match(effect, /if \(!live \|\| !payload\) return/);
  assert.doesNotMatch(effect, /forEach|for \(const .* of .*sets/, "never one request per Set");
  assert.equal((effect.match(/readFinancialHistoryCached\(/g) || []).length, 1, "a single cohort request");
});

test("range changes keep the last truthful chart and never show one range as another", () => {
  assert.match(chart, /request\.view\?\.mode === mode \? request\.view : null/);
  assert.match(chart, /display\?\.range \|\| range/);
  assert.match(chart, /windowKey,\s*\},\s*key: requestKey/);
  assert.match(chart, /if \(active\) setRequest\(commit\(payload\)\)|if \(active\)/);
  assert.match(chart, /return \(\) => \{ active = false; \};/);
});

test("access safety: chart is keyed by session identity and locks when not entitled", () => {
  assert.match(chart, /!entitled \? <LockedPreview \/>/);
  assert.match(chart, /shouldFetchFinancialRipHistory\(\{ entitled, authStatus/);
  assert.match(cache, /!entitled \|\| !\(authStatus === "resolved" \|\| authStatus === "degraded"\)/);
});

test("B1 styling is intact: green Sets/Eras and range buttons; Clear All is a dark-red pill, not a solid button", () => {
  assert.equal((chart.match(/RANKINGS_SELECTED_BORDERED_SURFACE/g) || []).length, 3);
  assert.doesNotMatch(chart, /bg-white\/10|border-sky-400\/40/);
  assert.match(legend, /border-red-400\/45 bg-red-500\/\[\.09\]/);
  assert.match(legend, /text-red-300/);
  assert.doesNotMatch(legend, /bg-red-[5-9]00(?![/\[])/);
});
