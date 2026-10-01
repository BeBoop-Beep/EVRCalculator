import assert from "node:assert/strict";
import test from "node:test";

import {
  FINANCIAL_RIP_WINDOWS,
  buildFinancialRipChartModel,
  eraFinancialRipCandidates,
  entitySeriesKey,
  financialRipRequestEntities,
  financialRipWindowRange,
  financialRipTooltipRows,
  formatFinancialRipDelta,
  formatFinancialRipTooltipDelta,
  nextSingleEraPreset,
  shouldFetchFinancialRipHistory,
  stableEntityColor,
  setFinancialRipCandidates,
  setIdsForEra,
  toggleFinancialRipSelection,
} from "./financialRipHistoryModel.mjs";

const selected = [{ entity_type: "set", entity_id: "set-a", name: "Set A" }];

test("single-era preset cycles bidirectionally through the available eras", () => {
  assert.equal(nextSingleEraPreset("sv", ["mega", "sv"]), "mega");
  assert.equal(nextSingleEraPreset("mega", ["mega", "sv"]), "sv");
  assert.equal(nextSingleEraPreset("sv", []), null);
});

test("plots only the certified absolute Financial RIP contract", () => {
  const model = buildFinancialRipChartModel([{
    metric_key: "financial",
    entity_id: "set-a",
    market_date: "2026-09-27",
    absolute_financial_rip_score: 34.8,
    overall_financial_rip_reference: 30.2,
    absolute_delta_vs_overall: 4.6,
    rank: 2,
    cohort_size: 22,
    benchmark_score: 8.7,
    modeled_return_on_spend: 0.41,
  }], selected, { startDate: "2026-09-27", endDate: "2026-09-27" });
  const point = model.points[0];
  assert.equal(point[entitySeriesKey("set-a")], 34.8);
  assert.equal(point.overallFinancialRip, 30.2);
  assert.deepEqual(point.entities["set-a"], {
    financialRip: 34.8,
    overallFinancialRip: 30.2,
    deltaVsOverall: 4.6,
    rank: 2,
    cohortSize: 22,
    status: null,
  });
});

test("actual observations connect without fabricating missing calendar days", () => {
  const rows = ["2026-09-25", "2026-09-27"].map((market_date, index) => ({
    metric_key: "financial", entity_id: "set-a", market_date,
    absolute_financial_rip_score: 30 + index,
    overall_financial_rip_reference: 28 + index,
  }));
  const model = buildFinancialRipChartModel(rows, selected, { startDate: "2026-09-25", endDate: "2026-09-27" });
  assert.deepEqual(model.points.map((point) => point.date), ["2026-09-25", "2026-09-27"]);
  assert.ok(!model.points.some((point) => point.date === "2026-09-26"));
  assert.deepEqual(model.points.map((point) => point[entitySeriesKey("set-a")]), [30, 31]);
});

test("all twelve certified v2 observations and the moving Overall reference survive", () => {
  const dates = ["2026-08-22", "2026-08-24", "2026-08-25", "2026-08-26", "2026-09-08", "2026-09-12", "2026-09-13", "2026-09-14", "2026-09-15", "2026-09-25", "2026-09-27", "2026-09-28"];
  const rows = dates.map((marketDate, index) => ({
    metricKey: "financial", entityId: "set-a", marketDate,
    absoluteFinancialRipScore: 31 + index,
    overallFinancialRipReference: 29 + (index * 0.1),
    absoluteDeltaVsOverall: 2 + (index * 0.9),
  }));
  const model = buildFinancialRipChartModel(rows, selected);
  assert.deepEqual(model.points.map((point) => point.date), dates);
  assert.deepEqual(model.points.map((point) => point.overallFinancialRip), dates.map((_, index) => 29 + (index * 0.1)));
  assert.ok(!model.points.some((point) => point.date === "2026-08-23"));
  assert.ok(model.points.every((point) => Number.isFinite(point.timestamp)));
});

test("timeframes and authority date match the chart contract", () => {
  assert.deepEqual(FINANCIAL_RIP_WINDOWS.map((item) => item.key), ["1D", "7D", "30D", "3M", "6M", "1Y", "ALL"]);
  assert.deepEqual(financialRipWindowRange("1D", "2026-09-27"), { startDate: "2026-09-27", endDate: "2026-09-27" });
  assert.deepEqual(financialRipWindowRange("7D", "2026-09-27"), { startDate: "2026-09-21", endDate: "2026-09-27" });
  assert.deepEqual(financialRipWindowRange("30D", "2026-09-27"), { startDate: "2026-08-29", endDate: "2026-09-27" });
  assert.deepEqual(financialRipWindowRange("ALL", "2026-09-27", "2026-01-04"), { startDate: "2026-01-04", endDate: "2026-09-27" });
});

test("tooltip deltas use directional benchmark indicators", () => {
  assert.equal(formatFinancialRipDelta(4.43), "↑ +4.43 vs Overall");
  assert.equal(formatFinancialRipDelta(-3.27), "↓ −3.27 vs Overall");
  assert.equal(formatFinancialRipDelta(0), "— 0.00 vs Overall");
});

test("compact tooltip rows sort by hovered score with stable ties and honest missing values", () => {
  const series = [
    { entity_id: "b", name: "Beta", color: "#b" },
    { entity_id: "a", name: "Alpha", color: "#a" },
    { entity_id: "missing", name: "Missing", color: "#m" },
    { entity_id: "top", name: "Top", color: "#t" },
  ];
  const rows = financialRipTooltipRows({ overallFinancialRip: 30, entities: {
    a: { financialRip: 32 }, b: { financialRip: 32 }, top: { financialRip: 35 }, missing: { financialRip: null },
  } }, series);
  assert.deepEqual(rows.map((row) => row.entity_id), ["top", "a", "b"]);
  assert.deepEqual(rows.map((row) => row.deltaVsOverall), [5, 2, 2]);
  assert.equal(formatFinancialRipTooltipDelta(5), "+5.00 \u2191");
  assert.equal(formatFinancialRipTooltipDelta(-2), "\u22122.00 \u2193");
  assert.equal(formatFinancialRipTooltipDelta(0), "\u00b10.00");
  assert.equal(financialRipTooltipRows({ overallFinancialRip: null, entities: { a: { financialRip: 32 } } }, series)[0].deltaVsOverall, null);
});

test("Overall-only mode retains authoritative observed references without entity series", () => {
  const model = buildFinancialRipChartModel([
    { entity_id: "a", market_date: "2026-09-25", absolute_financial_rip_score: 31, overall_financial_rip_reference: 29 },
    { entity_id: "a", market_date: "2026-09-27", absolute_financial_rip_score: 33, overall_financial_rip_reference: 30 },
  ], []);
  assert.deepEqual(model.series, []);
  assert.deepEqual(model.points.map((point) => [point.date, point.overallFinancialRip]), [["2026-09-25", 29], ["2026-09-27", 30]]);
  assert.ok(model.points.every((point) => Object.keys(point.entities).length === 0));
});

test("Overall-only window changes retain one transport anchor without rendering it", () => {
  const prior = [{ entity_type: "set", entity_id: "a", name: "Anchor" }, { entity_type: "set", entity_id: "b", name: "Other" }];
  assert.deepEqual(financialRipRequestEntities([], prior), [prior[0]]);
  assert.deepEqual(financialRipRequestEntities([prior[1]], prior), [prior[1]]);
  assert.deepEqual(financialRipRequestEntities([], []), []);
});

test("Basic and anonymous access cannot initiate history reads", () => {
  const ready = { selectedCount: 3, startDate: "2026-08-29", endDate: "2026-09-27" };
  assert.equal(shouldFetchFinancialRipHistory({ ...ready, entitled: false, authStatus: "resolved" }), false);
  assert.equal(shouldFetchFinancialRipHistory({ ...ready, entitled: false, authStatus: "degraded" }), false);
  assert.equal(shouldFetchFinancialRipHistory({ ...ready, entitled: true, authStatus: "loading" }), false);
  assert.equal(shouldFetchFinancialRipHistory({ ...ready, entitled: true, authStatus: "resolved" }), true);
});

test("selection supports a manual cap while an Era shortcut can show every member Set", () => {
  assert.deepEqual(toggleFinancialRipSelection(["1", "2", "3", "4", "5"], "6", 5), ["1", "2", "3", "4", "5"]);
  assert.deepEqual(toggleFinancialRipSelection(["1", "2", "3", "4", "5"], "6"), ["1", "2", "3", "4", "5", "6"]);
  assert.deepEqual(toggleFinancialRipSelection(["1", "2"], "1"), ["2"]);
  const candidates = setFinancialRipCandidates(
    [{ target_id: "a", name: "Set A" }, { target_id: "b", name: "Set B" }, { target_id: "c", name: "Set C" }],
    [{ setId: "a", eraId: "sv", eraName: "Scarlet & Violet" }, { setId: "b", eraId: "sv", eraName: "Scarlet & Violet" }, { setId: "c", eraId: "swsh", eraName: "Sword & Shield" }],
  );
  assert.deepEqual(setIdsForEra(candidates, "sv"), ["a", "b"]);
  assert.equal(candidates[0].eraName, "Scarlet & Violet");
  assert.equal(stableEntityColor("set-a"), stableEntityColor("set-a"));
});

test("Era presets exceed the manual five limit without truncation", () => {
  const candidates = Array.from({ length: 8 }, (_, index) => ({ entity_id: `s${index}`, eraId: "era" }));
  assert.equal(setIdsForEra(candidates, "era").length, 8);
  assert.equal(new Set(candidates.map((item) => stableEntityColor(item.entity_id))).size > 1, true);
  assert.equal(stableEntityColor("s6"), stableEntityColor("s6"));
});

test("the two public era identities are available together and requests stay typed", () => {
  const eras = eraFinancialRipCandidates([
    { eraId: "mega", eraName: "Mega Evolution" },
    { eraId: "sv", eraName: "Scarlet and Violet" },
    { eraId: "sv", eraName: "Scarlet and Violet" },
  ]);
  assert.deepEqual(eras, [
    { entity_type: "era", entity_id: "mega", name: "Mega Evolution" },
    { entity_type: "era", entity_id: "sv", name: "Scarlet and Violet" },
  ]);
  assert.ok(eras.every((item) => item.entity_type === "era"));
  assert.ok(selected.every((item) => item.entity_type === "set"));
});
