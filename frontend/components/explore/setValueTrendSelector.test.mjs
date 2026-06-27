import test from "node:test";
import assert from "node:assert/strict";

import { selectOverviewSetValueTrendByScope } from "./setValueTrendSelector.mjs";

const scopedHistories = {
  standard: [
    { date: "2099-01-01", setValue: 100, valueScope: "standard" },
    { date: "2099-01-16", setValue: 105, valueScope: "standard" },
    { date: "2099-01-31", setValue: 110, valueScope: "standard" },
  ],
  hits: [
    { date: "2099-01-01", setValue: 50, valueScope: "hits" },
    { date: "2099-01-16", setValue: 65, valueScope: "hits" },
    { date: "2099-01-31", setValue: 80, valueScope: "hits" },
  ],
  top10: [
    { date: "2099-01-01", setValue: 25, valueScope: "top10" },
    { date: "2099-01-16", setValue: 30, valueScope: "top10" },
    { date: "2099-01-31", setValue: 40, valueScope: "top10" },
  ],
};

function select(scope, overrides = {}) {
  return selectOverviewSetValueTrendByScope({
    history: scopedHistories.standard,
    historiesByScope: scopedHistories,
    selectedScope: scope,
    selectedWindowKey: "30D",
    ...overrides,
  });
}

test("selectedScope=checklist returns checklist label, value, series, and deltas", () => {
  const selected = select("standard");

  assert.equal(selected.scope, "standard");
  assert.equal(selected.label, "Checklist");
  assert.equal(selected.metricLabel, "Checklist Set Value");
  assert.equal(selected.currentValue, 110);
  assert.equal(selected.delta30d, 10);
  assert.equal(selected.delta30dPct, 10);
  assert.deepEqual(selected.series.map((point) => point.setValue), [100, 105, 110]);
  assert.equal(selected.diagnostics.source, "setValueHistoriesByScope.standard");
});

test("selectedScope=hits returns hits label, value, series, and deltas", () => {
  const selected = select("hits");

  assert.equal(selected.scope, "hits");
  assert.equal(selected.label, "Hits");
  assert.equal(selected.metricLabel, "Hits Set Value");
  assert.equal(selected.currentValue, 80);
  assert.equal(selected.delta30d, 30);
  assert.equal(selected.delta30dPct, 60);
  assert.deepEqual(selected.series.map((point) => point.setValue), [50, 65, 80]);
  assert.equal(selected.diagnostics.source, "setValueHistoriesByScope.hits");
});

test("selectedScope=top10 returns top10 label, value, series, and deltas", () => {
  const selected = select("top10");

  assert.equal(selected.scope, "top10");
  assert.equal(selected.label, "Top 10");
  assert.equal(selected.metricLabel, "Top 10 Set Value");
  assert.equal(selected.currentValue, 40);
  assert.equal(selected.delta30d, 15);
  assert.equal(selected.delta30dPct, 60);
  assert.deepEqual(selected.series.map((point) => point.setValue), [25, 30, 40]);
  assert.equal(selected.diagnostics.source, "setValueHistoriesByScope.top10");
});

test("active pill scope and selected chart data use the same requested scope", () => {
  const expectedCurrentValues = {
    standard: 110,
    hits: 80,
    top10: 40,
  };

  for (const scope of ["standard", "hits", "top10", "standard"]) {
    const selected = select(scope);

    assert.equal(selected.scope, scope);
    assert.equal(selected.diagnostics.selectedScope, selected.scope);
    assert.equal(selected.currentValue, expectedCurrentValues[scope]);
    assert.equal(selected.series.at(-1)?.valueScope, scope);
  }
});

test("missing one scope does not silently fall back to another scope", () => {
  const selected = selectOverviewSetValueTrendByScope({
    history: scopedHistories.standard,
    historiesByScope: { standard: scopedHistories.standard },
    selectedScope: "hits",
    selectedWindowKey: "30D",
  });

  assert.equal(selected.scope, "hits");
  assert.equal(selected.label, "Hits");
  assert.equal(selected.currentValue, null);
  assert.deepEqual(selected.series, []);
  assert.equal(selected.diagnostics.source, null);
  assert.equal(selected.diagnostics.hasRequestedScopeHistory, false);
  assert.equal(selected.diagnostics.missingRequestedScope, true);
  assert.deepEqual(selected.diagnostics.pointCountsByScope, { standard: 3 });
});

test("set value trend deltas use latest observed point instead of carried-forward today", () => {
  const selected1D = selectOverviewSetValueTrendByScope({
    historiesByScope: {
      hits: [
        { date: "2026-06-20", setValue: 729.07, valueScope: "hits" },
        { date: "2026-06-23", setValue: 732.87, valueScope: "hits" },
        { date: "2026-06-24", setValue: 734.52, valueScope: "hits" },
        { date: "2026-06-25", setValue: 734.52, valueScope: "hits", isCarriedForward: true, sourceDate: "2026-06-24" },
        { date: "2026-06-26", setValue: 734.52, valueScope: "hits", isCarriedForward: true, sourceDate: "2026-06-24" },
      ],
    },
    selectedScope: "hits",
    selectedWindowKey: "1D",
  });
  const selected7D = selectOverviewSetValueTrendByScope({
    historiesByScope: {
      hits: selected1D.points,
    },
    selectedScope: "hits",
    selectedWindowKey: "7D",
  });

  assert.equal(selected1D.currentValue, 734.52);
  assert.equal(selected1D.lastPoint.date, "2026-06-24");
  assert.equal(Number(selected1D.deltaAmount.toFixed(2)), 1.65);
  assert.equal(selected1D.selectedWindow.startDate, "2026-06-23");
  assert.equal(selected1D.selectedWindow.endDate, "2026-06-24");
  assert.equal(selected7D.selectedWindow.endDate, "2026-06-24");
  assert.equal(selected7D.lastPoint.date, "2026-06-24");
  assert.ok(selected1D.points.some((point) => point.date === "2026-06-26" && point.isCarriedForward));
});

test("set value trend returns N/A delta when only one observed point exists before carried-forward rows", () => {
  const selected = selectOverviewSetValueTrendByScope({
    historiesByScope: {
      standard: [
        { date: "2026-06-24", setValue: 734.52 },
        { date: "2026-06-25", setValue: 734.52, isCarriedForward: true, sourceDate: "2026-06-24" },
        { date: "2026-06-26", setValue: 734.52, isCarriedForward: true, sourceDate: "2026-06-24" },
      ],
    },
    selectedScope: "standard",
    selectedWindowKey: "1D",
  });

  assert.equal(selected.currentValue, 734.52);
  assert.equal(selected.lastPoint.date, "2026-06-24");
  assert.equal(selected.deltaAmount, null);
  assert.equal(selected.deltaPercent, null);
  assert.equal(selected.hasTrend, false);
});
