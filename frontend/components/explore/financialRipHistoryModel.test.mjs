import assert from "node:assert/strict";
import test from "node:test";

import {
  FINANCIAL_RIP_WINDOWS,
  buildFinancialRipChartModel,
  eraFinancialRipCandidates,
  entitySeriesKey,
  financialRipWindowRange,
  shouldFetchFinancialRipHistory,
  stableEntityColor,
  setFinancialRipCandidates,
  setIdsForEra,
  toggleFinancialRipSelection,
} from "./financialRipHistoryModel.mjs";

const selected = [{ entity_type: "set", entity_id: "set-a", name: "Set A" }];

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

test("daily domain leaves missing publications as truthful null gaps", () => {
  const rows = ["2026-09-25", "2026-09-27"].map((market_date, index) => ({
    metric_key: "financial", entity_id: "set-a", market_date,
    absolute_financial_rip_score: 30 + index,
    overall_financial_rip_reference: 28 + index,
  }));
  const model = buildFinancialRipChartModel(rows, selected, { startDate: "2026-09-25", endDate: "2026-09-27" });
  assert.deepEqual(model.points.map((point) => point.date), ["2026-09-25", "2026-09-26", "2026-09-27"]);
  assert.equal(model.points[1][entitySeriesKey("set-a")], undefined);
  assert.equal(model.points[1].overallFinancialRip, null);
});

test("timeframes and authority date match the chart contract", () => {
  assert.deepEqual(FINANCIAL_RIP_WINDOWS.map((item) => item.key), ["30D", "3M", "6M", "1Y", "ALL"]);
  assert.deepEqual(financialRipWindowRange("30D", "2026-09-27"), { startDate: "2026-08-29", endDate: "2026-09-27" });
  assert.deepEqual(financialRipWindowRange("ALL", "2026-09-27", "2026-01-04"), { startDate: "2026-01-04", endDate: "2026-09-27" });
});

test("Basic and anonymous access cannot initiate history reads", () => {
  const ready = { selectedCount: 3, startDate: "2026-08-29", endDate: "2026-09-27" };
  assert.equal(shouldFetchFinancialRipHistory({ ...ready, entitled: false, authStatus: "resolved" }), false);
  assert.equal(shouldFetchFinancialRipHistory({ ...ready, entitled: false, authStatus: "degraded" }), false);
  assert.equal(shouldFetchFinancialRipHistory({ ...ready, entitled: true, authStatus: "loading" }), false);
  assert.equal(shouldFetchFinancialRipHistory({ ...ready, entitled: true, authStatus: "resolved" }), true);
});

test("set selection is uncapped so an Era shortcut can show every member Set", () => {
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
