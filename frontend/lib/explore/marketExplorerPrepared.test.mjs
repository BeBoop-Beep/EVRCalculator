import assert from "node:assert/strict";
import test from "node:test";
import { buildPreparedSeries, groupPreparedDirectory, QUICK_MARKET_KEYS } from "./marketExplorerPrepared.mjs";

const era = { market_key: "era:e1", market_type: "era", era_id: "e1", label: "Scarlet & Violet" };
const set = { market_key: "set:s1", market_type: "set", set_id: "s1", parent_era_id: "e1", label: "Temporal Forces", current_value: 123, source_as_of: "2026-09-10", comparison_as_of: "2026-09-08", comparison_value: 120, comparison_index_value: 105, history_available: true, return_7d_pct: 2, return_30d_pct: 4, return_90d_pct: 8, return_1y_pct: null };

test("directory groups Sets by canonical parent Era and keeps alphabetical browse free", () => {
  const grouped = groupPreparedDirectory([set, era]);
  assert.equal(grouped.eras.length, 1);
  assert.equal(grouped.sets[0].era.market_key, era.market_key);
  assert.equal(grouped.sets[0].rows[0].market_key, set.market_key);
});

test("accepted directory inventory exposes all 106 Sets and 17 Eras", () => {
  const eras = Array.from({ length: 17 }, (_, index) => ({ market_key: `era:${index}`, market_type: "era", era_id: `e${index}`, label: `Era ${index}` }));
  const sets = Array.from({ length: 106 }, (_, index) => ({ market_key: `set:${index}`, market_type: "set", parent_era_id: `e${index % 17}`, label: `Set ${String(index).padStart(3, "0")}` }));
  const grouped = groupPreparedDirectory([...eras, ...sets]);
  assert.equal(grouped.eras.length, 17);
  assert.equal(grouped.sets.reduce((sum, group) => sum + group.rows.length, 0), 106);
});

test("the exact six prepared Quick Market identities exclude contextual Top 10", () => {
  assert.equal(QUICK_MARKET_KEYS.length, 6);
  assert.ok(QUICK_MARKET_KEYS.includes("curated:global-top10"));
  assert.ok(!QUICK_MARKET_KEYS.some((key) => key.includes("selected-set")));
});

test("comparison uses comparison fields and preserves honest unavailable 1Y", () => {
  const [series] = buildPreparedSeries([set], [{ market_key: "set:s1", market_date: "2026-09-08", index_value: 105, tracked_value: 120 }]);
  assert.equal(series.browseValue, 123);
  assert.equal(series.basketValue, 120);
  assert.equal(series.sourceAsOf, "2026-09-10");
  assert.equal(series.comparisonAsOf, "2026-09-08");
  assert.equal(series.familyChanges["1Y"].available, false);
  assert.equal(series.trend[0].value, 105);
});

test("browse-only Sets remain selectable while comparison history is unavailable", () => {
  const [series] = buildPreparedSeries([{ ...set, history_available: false, comparison_value: null, comparison_index_value: null }], []);
  assert.equal(series.available, true);
  assert.equal(series.historyAvailable, false);
  assert.deepEqual(series.trend, []);
});
