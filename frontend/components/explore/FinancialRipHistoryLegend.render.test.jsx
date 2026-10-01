import "../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import FinancialRipHistoryLegend, { CLEAR_ALL_LABEL } from "./FinancialRipHistoryLegend.jsx";
import ChartTooltip, { FinancialRipTooltipContent } from "./FinancialRipHistoryTooltip.jsx";
import { buildFinancialRipChartModel } from "./financialRipHistoryModel.mjs";

const sets = Array.from({ length: 16 }, (_, i) => ({ entity_type: "set", entity_id: `s${i + 1}`, name: `Set ${String(i + 1).padStart(2, "0")}` }));
const rows = sets.map((set, i) => ({ entityId: set.entity_id, marketDate: "2026-09-30", absoluteFinancialRipScore: 4 + i * 0.2, overallFinancialRipReference: 5, absoluteDeltaVsOverall: -1 + i * 0.2 }));
const model = buildFinancialRipChartModel(rows, sets, { startDate: "2026-09-01", endDate: "2026-09-30" });
const legend = (props) => renderToStaticMarkup(<FinancialRipHistoryLegend series={model.series} {...props} />);

test("each key is two distinct controls: a focus button and a separate remove button", () => {
  const html = legend({});
  assert.equal((html.match(/data-legend-focus/g) || []).length, 16);
  assert.equal((html.match(/data-legend-remove/g) || []).length, 16);
  const key = html.slice(html.indexOf('data-legend-entity="s1"'), html.indexOf('data-legend-entity="s2"'));
  assert.equal((key.match(/<button/g) || []).length, 2);
  assert.match(key, /aria-label="Focus Set 01 on Financial RIP chart"/);
  assert.match(key, /aria-label="Remove Set 01 from Financial RIP chart"/);
  assert.ok(key.indexOf("data-legend-focus") < key.indexOf("data-legend-remove"));
});

test("persistent focus is announced with aria-pressed and offers to clear; others stay selected", () => {
  const html = legend({ persistentFocusId: "s3" });
  const key = html.slice(html.indexOf('data-legend-entity="s3"'), html.indexOf('data-legend-entity="s4"'));
  assert.match(key, /aria-pressed="true"/);
  assert.match(key, /aria-label="Clear focus on Set 03 on Financial RIP chart"/);
  assert.match(key, /data-focused="true"/);
  assert.equal((html.match(/aria-pressed="false"/g) || []).length, 15);
  assert.equal((html.match(/data-legend-entity=/g) || []).length, 16, "focus never removes keys");
});

test("Overall is a permanent, non-interactive key; it can never be removed", () => {
  const html = legend({});
  const start = html.indexOf("data-legend-overall");
  const overall = html.slice(start, html.indexOf("data-legend-entity", start));
  assert.ok(overall.includes("Overall Financial RIP"));
  assert.ok(!overall.includes("<button"));
  assert.equal(legend({ series: [] }).includes("data-legend-overall"), true, "Overall stays with an empty selection");
});

test("Clear All: red-tinted pill, exact accessible name, same row as the keys, disabled when nothing is selected", () => {
  const html = legend({});
  const clear = html.slice(html.indexOf("data-financial-history-clear-all") - 40, html.indexOf("</button>", html.indexOf("data-financial-history-clear-all")));
  assert.equal(CLEAR_ALL_LABEL, "Clear all Financial RIP series");
  assert.ok(clear.includes('aria-label="Clear all Financial RIP series"'));
  assert.match(clear, /rounded-full/);
  assert.match(clear, /border-red-400\/45/);
  assert.match(clear, /bg-red-500\/\[\.09\]/);
  assert.match(clear, /text-red-300/);
  assert.doesNotMatch(clear, /bg-red-500 |bg-red-600|bg-red-700|text-white/);
  assert.ok(clear.includes(">Clear All"));
  assert.ok(!/disabled=""/.test(clear));
  const empty = legend({ series: [] });
  assert.ok(/data-financial-history-clear-all[^>]*disabled=""/.test(empty) || /disabled=""[^>]*data-financial-history-clear-all/.test(empty));
  // one legend row: Clear All lives beside (not below) the key container
  assert.equal((html.match(/data-financial-history-legend/g) || []).length, 1);
});

test("a 16-Set legend keeps every key, wraps, scrolls, and keeps Clear All outside the scroller", () => {
  const html = legend({});
  assert.equal((html.match(/data-legend-entity=/g) || []).length, 16);
  assert.match(html, /flex flex-wrap/);
  assert.match(html, /max-h-36[^"]*overflow-y-auto/);
  assert.ok(html.indexOf("data-financial-history-clear-all") > html.lastIndexOf("data-legend-remove"));
  assert.ok(/min-h-9/.test(html) && /min-w-9/.test(html), "touch targets");
});

test("hover focus is pointer-only: handlers ignore touch/pen pointers", () => {
  const calls = [];
  const tree = FinancialRipHistoryLegend({ series: model.series.slice(0, 1), onHoverFocus: (id) => calls.push(id) });
  const find = (node, pred) => { if (Array.isArray(node)) { for (const item of node) { const hit = find(item, pred); if (hit) return hit; } return null; } if (!node || typeof node !== "object") return null; if (pred(node)) return node; return find(node.props?.children ?? null, pred); };
  const body = find(tree, (n) => n.props && "data-legend-focus" in n.props);
  body.props.onPointerEnter({ pointerType: "touch" });
  body.props.onPointerLeave({ pointerType: "pen" });
  assert.deepEqual(calls, []);
  body.props.onPointerEnter({ pointerType: "mouse" });
  body.props.onPointerLeave({ pointerType: "mouse" });
  assert.deepEqual(calls, ["s1", null]);
});

test("normal tooltip: date and Overall once, all 16 selected rows, real vertical scroll region", () => {
  const point = model.points[0];
  const html = renderToStaticMarkup(<ChartTooltip active payload={[{ payload: point }]} series={model.series} />);
  assert.equal((html.match(/>Overall</g) || []).length, 1);
  assert.equal((html.match(/Set \d\d/g) || []).length, 16);
  assert.match(html, /max-h-\[min\(18rem,55vh\)\]/);
  const region = html.slice(html.indexOf("data-financial-history-tooltip-scroll"), html.indexOf(">", html.indexOf("data-financial-history-tooltip-scroll")));
  assert.match(region, /overflow-y-auto/);
  assert.match(region, /overscroll-contain/);
  assert.match(region, /touch-action:pan-y/);
  assert.match(region, /overscroll-behavior:contain/);
  assert.match(html, /min-h-0 flex-1|min-h-0/);
});

test("focused tooltip (persistent or hover) shows only the focused entity plus Overall", () => {
  const point = model.points[0];
  const html = renderToStaticMarkup(<ChartTooltip active payload={[{ payload: point }]} series={model.series} focusId="s7" />);
  assert.equal((html.match(/Set \d\d/g) || []).length, 1);
  assert.ok(html.includes("Set 07"));
  assert.equal((html.match(/>Overall</g) || []).length, 1);
  assert.match(html, /data-focused="true"/);
});

test("tooltip can be suppressed while a pinned panel is open, and the pinned panel is keyboard/touch scrollable", () => {
  const point = model.points[0];
  assert.equal(renderToStaticMarkup(<ChartTooltip active payload={[{ payload: point }]} series={model.series} suppressed />), "");
  const pinned = renderToStaticMarkup(<FinancialRipTooltipContent point={point} series={model.series} pinned onClose={() => {}} />);
  assert.match(pinned, /data-pinned="true"/);
  assert.match(pinned, /tabindex="0"/i);
  assert.match(pinned, /aria-label="Close pinned Financial RIP details"/);
  assert.match(pinned, /role="region"/);
});
