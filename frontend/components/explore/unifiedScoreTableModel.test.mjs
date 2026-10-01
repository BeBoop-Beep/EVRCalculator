import assert from "node:assert/strict";
import test from "node:test";
import { ariaSort, DEFAULT_SORT, displayedRank, effectiveSort, filterScoreRows, mergeScorecardRows, nextSort, publicOnlyRows, sortableKeys, sortScoreRows } from "./unifiedScoreTableModel.mjs";

const metric = (score, rank, tier, cohortSize = 3) => ({ score, rank, tier, cohortSize });
const rows = [
  { entityId: "a", name: "Alpha", era: { eraName: "One" }, overall: metric(7, 1, "S"), financial: metric(4.9, 3, "C"), collector: metric(5.5, 2, "B"), chase: metric(6, 1, "A") },
  { entityId: "b", name: "Beta", era: { eraName: "Two" }, overall: metric(6, 2, "A"), financial: metric(6.5, 1, "S"), collector: metric(6, 1, "A"), chase: metric(4, 3, "D") },
  { entityId: "c", name: "Gamma", era: { eraName: "One" }, overall: metric(4.6, 3, "D"), financial: metric(5.6, 2, "B"), collector: metric(4.9, 3, "C"), chase: metric(5.5, 2, "B") },
];
const ids = (list) => list.map((row) => row.entityId);

test("each metric sorts by its OWN canonical rank and the displayed rank follows it", () => {
  assert.deepEqual(ids(sortScoreRows(rows, { key: "overall", direction: "asc" })), ["a", "b", "c"]);
  assert.deepEqual(ids(sortScoreRows(rows, { key: "financial", direction: "asc" })), ["b", "c", "a"]);
  assert.deepEqual(ids(sortScoreRows(rows, { key: "collector", direction: "asc" })), ["b", "a", "c"]);
  assert.deepEqual(ids(sortScoreRows(rows, { key: "chase", direction: "asc" })), ["a", "c", "b"]);
  const financial = sortScoreRows(rows, { key: "financial", direction: "asc" });
  assert.deepEqual(financial.map((row) => displayedRank(row, "financial").rank), [1, 2, 3]);
  assert.equal(displayedRank(financial[0], "overall").rank, 2);
});

test("reverse sort is worst-to-best and unranked rows stay last either way", () => {
  assert.deepEqual(ids(sortScoreRows(rows, { key: "financial", direction: "desc" })), ["a", "c", "b"]);
  const withGap = [...rows, { entityId: "z", name: "Zed", overall: metric(5, 4, "C", 4) }];
  assert.equal(sortScoreRows(withGap, { key: "financial", direction: "asc" }).at(-1).entityId, "z");
  assert.equal(sortScoreRows(withGap, { key: "financial", direction: "desc" }).at(-1).entityId, "z");
});

test("ties keep a deterministic identity order and sorting never mutates input", () => {
  const tied = [{ entityId: "2", name: "B", overall: metric(5, 1, "C", 2) }, { entityId: "1", name: "A", overall: metric(5, 1, "C", 2) }];
  const before = JSON.stringify(tied);
  assert.deepEqual(ids(sortScoreRows(tied)), ["1", "2"]);
  assert.equal(JSON.stringify(tied), before);
});

test("search and Era filtering do not recompute canonical rank or tier", () => {
  const filtered = filterScoreRows(rows, { query: "alp" });
  assert.deepEqual(ids(filtered), ["a"]);
  assert.equal(filtered[0].financial.rank, 3);
  assert.equal(filtered[0].financial.cohortSize, 3);
  assert.equal(filtered[0].financial.tier, "C");
  assert.deepEqual(ids(filterScoreRows(rows, { eraFilter: "one" })), ["a", "c"]);
  assert.equal(filterScoreRows(rows, { eraFilter: "one" })[1].overall.rank, 3);
});

test("click contract: first click best-to-worst, second reverses, protected columns locked", () => {
  let sort = nextSort(DEFAULT_SORT, "financial", true);
  assert.deepEqual(sort, { key: "financial", direction: "asc" });
  sort = nextSort(sort, "financial", true);
  assert.deepEqual(sort, { key: "financial", direction: "desc" });
  assert.deepEqual(nextSort(DEFAULT_SORT, "chase", false), DEFAULT_SORT);
  assert.deepEqual(sortableKeys(false), ["overall"]);
  assert.deepEqual(sortableKeys(true), ["overall", "financial", "collector", "chase"]);
  assert.deepEqual(effectiveSort({ key: "chase", direction: "desc" }, false), DEFAULT_SORT);
  assert.equal(ariaSort({ key: "chase", direction: "desc" }, "chase"), "descending");
  assert.equal(ariaSort({ key: "chase", direction: "desc" }, "overall"), "none");
});

test("public scorecards never carry component values, even if the payload did", () => {
  const leaky = [{ entityId: "a", name: "A", overall: metric(7, 1, "S"), financial: metric(1, 1, "S"), collector: metric(1, 1, "S"), chase: metric(1, 1, "S") }];
  const merged = mergeScorecardRows({ rows: leaky, marketDate: "2026-09-30" }, null);
  assert.deepEqual(Object.keys(merged.rows[0]).sort(), ["entityId", "name", "overall"]);
  assert.equal(JSON.stringify(publicOnlyRows(leaky)).includes("financial"), false);
  assert.equal(merged.paid, false);
});

test("paid scorecards fill all four metrics for the same publication and keep public identity", () => {
  const publicCard = { marketDate: "2026-09-30", rows: [{ entityId: "mega", name: "Mega Evolution", logoImageUrl: "/logo.png", overall: metric(4.602, 2, "D", 2) }] };
  const paidCard = { marketDate: "2026-09-30", rows: [{ entityId: "mega", name: "Mega Evolution", modeledSetCount: 5, overall: metric(4.602, 2, "D", 2), financial: metric(4.604, 2, "D", 2), chase: metric(4.306, 2, "D", 2), collector: metric(4.989, 2, "C", 2) }] };
  const merged = mergeScorecardRows(publicCard, paidCard);
  const [mega] = merged.rows;
  assert.equal(merged.paid, true);
  assert.equal(mega.financial.score, 4.604);
  assert.equal(mega.chase.score, 4.306);
  assert.equal(mega.collector.score, 4.989);
  assert.equal(mega.logoImageUrl, "/logo.png");
  assert.equal(mega.overall.tier, "D");
});

test("a different paid publication replaces the public cohort wholesale", () => {
  const merged = mergeScorecardRows({ marketDate: "2026-09-29", rows: [{ entityId: "old", name: "Old", overall: metric(5, 1, "C", 1) }] }, { marketDate: "2026-09-30", rows: [{ entityId: "new", name: "New", overall: metric(6, 1, "A", 1) }] });
  assert.deepEqual(ids(merged.rows), ["new"]);
});
