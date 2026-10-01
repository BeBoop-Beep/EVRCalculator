import assert from "node:assert/strict";
import test from "node:test";
import {
  FINANCIAL_RIP_FADED_OPACITY,
  buildFinancialRipChartModel,
  financialRipRequestEntities,
  financialRipTooltipRows,
  orderSeriesForDrawing,
  resolveActiveFocus,
  seriesEmphasis,
  toggleFocus,
} from "./financialRipHistoryModel.mjs";

const sets = Array.from({ length: 16 }, (_, i) => ({ entity_type: "set", entity_id: `s${i + 1}`, name: `Set ${String(i + 1).padStart(2, "0")}` }));
const rows = sets.map((set, i) => ({ entityId: set.entity_id, marketDate: "2026-09-30", absoluteFinancialRipScore: 4 + i * 0.2, overallFinancialRipReference: 5, absoluteDeltaVsOverall: -1 + i * 0.2, rank: i + 1, cohortSize: 22 }));
const model = buildFinancialRipChartModel(rows, sets, { startDate: "2026-09-01", endDate: "2026-09-30" });
const point = model.points[0];

test("focus resolution: hover is temporary and wins; persistent returns on leave; unplotted ids are ignored", () => {
  const ids = ["s1", "s2", "s3"];
  assert.equal(resolveActiveFocus({ persistentId: "s1", hoverId: null, seriesIds: ids }), "s1");
  assert.equal(resolveActiveFocus({ persistentId: "s1", hoverId: "s2", seriesIds: ids }), "s2");
  assert.equal(resolveActiveFocus({ persistentId: "s1", hoverId: null, seriesIds: ids }), "s1", "leaving hover restores persistent focus");
  assert.equal(resolveActiveFocus({ persistentId: null, hoverId: null, seriesIds: ids }), null, "all-series view when nothing is focused");
  assert.equal(resolveActiveFocus({ persistentId: "gone", hoverId: null, seriesIds: ids }), null, "removing the focused entity clears focus");
  assert.equal(resolveActiveFocus({ persistentId: null, hoverId: "gone", seriesIds: ids }), null);
});

test("clicking the focused key again clears persistent focus; another key moves it", () => {
  assert.equal(toggleFocus(null, "s1"), "s1");
  assert.equal(toggleFocus("s1", "s1"), null);
  assert.equal(toggleFocus("s1", "s2"), "s2");
});

test("focused series keeps full emphasis; the rest fade strongly and lose dots; no focus = no fade", () => {
  assert.deepEqual(seriesEmphasis("s1", "s1"), { faded: false, strokeOpacity: 1, strokeWidth: 1.75, showDots: true });
  const other = seriesEmphasis("s2", "s1");
  assert.equal(other.faded, true);
  assert.equal(other.strokeOpacity, FINANCIAL_RIP_FADED_OPACITY);
  assert.ok(other.strokeOpacity <= 0.2);
  assert.equal(other.strokeWidth, 1.75);
  assert.equal(other.showDots, false);
  assert.equal(seriesEmphasis("s2", null).faded, false);
});

test("the focused series is drawn last without changing membership", () => {
  const ordered = orderSeriesForDrawing(model.series, "s3");
  assert.equal(ordered.at(-1).entity_id, "s3");
  assert.equal(ordered.length, 16);
  assert.deepEqual(orderSeriesForDrawing(model.series, null), model.series);
});

test("normal tooltip lists every selected row, sorted by value descending", () => {
  const list = financialRipTooltipRows(point, model.series);
  assert.equal(list.length, 16);
  assert.deepEqual(list.map((r) => r.entity_id), [...sets].reverse().map((s) => s.entity_id));
  assert.ok(list.every((r) => Math.abs(r.deltaVsOverall - (r.score - 5)) < 1e-9), "delta = same-date entity minus same-date Overall");
});

test("focused tooltip shows ONLY the focused entity; Overall stays on the point", () => {
  const list = financialRipTooltipRows(point, model.series, "s5");
  assert.deepEqual(list.map((r) => r.entity_id), ["s5"]);
  assert.equal(point.overallFinancialRip, 5);
  assert.deepEqual(financialRipTooltipRows(point, model.series, "not-plotted"), []);
});

test("Clear All state: no plotted series, Overall still on every point, selection state untouched by focus", () => {
  const cleared = buildFinancialRipChartModel(rows, [], { startDate: "2026-09-01", endDate: "2026-09-30" });
  assert.deepEqual(cleared.series, []);
  assert.equal(cleared.points.length, 1);
  assert.equal(cleared.points[0].overallFinancialRip, 5);
  assert.deepEqual(Object.keys(cleared.points[0].entities), [], "the transport anchor is never a rendered series");
  assert.ok(!Object.keys(cleared.points[0]).some((k) => k.startsWith("entity_")));
});

test("Overall-only range change still has an authorised transport anchor (never lost, never plotted)", () => {
  const cohort = sets.slice(0, 22);
  assert.deepEqual(financialRipRequestEntities([], [], cohort).map((e) => e.entity_id), ["s1"]);
  assert.deepEqual(financialRipRequestEntities([], [sets[4]], cohort).map((e) => e.entity_id), ["s5"]);
  assert.deepEqual(financialRipRequestEntities([sets[2]], [sets[4]], cohort).map((e) => e.entity_id), ["s3"]);
  assert.deepEqual(financialRipRequestEntities([], [], []), []);
});
