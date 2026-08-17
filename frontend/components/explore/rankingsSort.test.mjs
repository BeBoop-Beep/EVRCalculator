// Behavioural tests for Rankings column sorting.
//
// rankingsSort.mjs is dependency-free (it imports only exploreRankingConfig.mjs
// and canonicalRipV7.mjs, both of which are themselves import-free), so this
// exercises the REAL ordering rather than asserting on component source strings.
//
// Every fixture below is synthetic. No real set name, rank, price, EV or score
// is hardcoded anywhere in this file or in the module under test.

import test from "node:test";
import assert from "node:assert/strict";

import {
  RANKINGS_DEFAULT_SORT,
  RANKINGS_SORT_COLUMNS,
  RANKINGS_SORT_COLUMN_IDS,
  SORT_ASC,
  SORT_DESC,
  ariaSortFor,
  nextSortState,
  readAverageLoss,
  readCollectorAppealBlock,
  readModelBreakEven,
  readSortValue,
  readTypicalOpening,
  sortRankingsRows,
} from "./rankingsSort.mjs";

/**
 * A target shaped like the real `/explore/rip-statistics/targets` row: the
 * canonical V7 contract bundle plus the top-level V7/V3 objects and the flat
 * simulation columns.
 */
function makeTarget({
  name,
  overallRank = null,
  overall = null,
  financial = null,
  collectorAppeal = null,
  collectorAppealRank = null,
  meanValue = null,
  medianValue = null,
  packCost = null,
  probProfit = null,
  topChaseMarketValue = null,
  averageLossWhenLosing = null,
}) {
  return {
    name,
    target_type: "pokemon_set",
    target_id: name,
    overallRipV9: { relativeScore: overall, rank: overallRank, cohortSize: 4, tier: "B" },
    financialRipV3: { relativeScore: financial, rank: overallRank, cohortSize: 4, tier: "B" },
    publicRipContractV9: {
      overallRip: { relativeScore: overall, rank: overallRank, rankedSetCount: 4 },
      financialRip: { relativeScore: financial, rank: overallRank, rankedSetCount: 4 },
      collectorAppeal: {
        relativeScore: collectorAppeal,
        absoluteScore: collectorAppeal === null ? null : collectorAppeal / 2,
        rank: collectorAppealRank,
        rankedSetCount: 4,
        tier: "C",
      },
    },
    mean_value: meanValue,
    median_value: medianValue,
    pack_cost: packCost,
    prob_profit: probProfit,
    rankingsChase: topChaseMarketValue === null ? undefined : { cardName: `${name} chase`, currentMarketPrice: topChaseMarketValue, impliedOddsOneInN: 100 },
    // Average Loss When Losing, published by the simulation. Deliberately NOT
    // consistent with pack_cost - mean_value in these fixtures, so any test that
    // passes would fail the moment the old unconditional expression came back.
    expected_loss_when_losing: averageLossWhenLosing,
  };
}

// Digit lengths chosen so that a lexicographic ("100" < "9" < "95") sort is
// unmistakably different from a numeric one, for every column.
const ALPHA = makeTarget({
  name: "alpha",
  overallRank: 1,
  overall: 100,
  financial: 100,
  collectorAppeal: 9,
  collectorAppealRank: 3,
  meanValue: 9.8,
  medianValue: 9.5,
  packCost: 100.5,
  probProfit: 0.098,
  averageLossWhenLosing: 9.5,
  topChaseMarketValue: 9,
});
const BRAVO = makeTarget({
  name: "bravo",
  overallRank: 2,
  overall: 95,
  financial: 9,
  collectorAppeal: 95,
  collectorAppealRank: 1,
  meanValue: 100.25,
  medianValue: 100.25,
  packCost: 9.8,
  probProfit: 0.741,
  averageLossWhenLosing: 100.25,
  topChaseMarketValue: 100,
});
const CHARLIE = makeTarget({
  name: "charlie",
  overallRank: 3,
  overall: 9,
  financial: 95,
  collectorAppeal: 100,
  collectorAppealRank: 2,
  meanValue: 95.5,
  medianValue: 95.5,
  packCost: 9.75,
  probProfit: 0.041,
  averageLossWhenLosing: 95.5,
  topChaseMarketValue: 95,
});
// Every sortable metric unavailable. Not zero — absent.
const DELTA = makeTarget({ name: "delta", overallRank: 4 });

const CANONICAL = [ALPHA, BRAVO, CHARLIE, DELTA];

function names(rows) {
  return rows.map((row) => row.name);
}

/* ------------------------------------------------ the seven metrics exist --- */

test("all required Rankings metrics are sortable columns", () => {
  assert.deepEqual(RANKINGS_SORT_COLUMN_IDS, [
    "overall",
    "financial",
    "collectorAppeal",
    "typicalOpening",
    "modelBreakEven",
    "marketPrice",
    "chanceToBeatCost",
    "topChase",
  ]);
  assert.deepEqual(
    RANKINGS_SORT_COLUMN_IDS.map((id) => RANKINGS_SORT_COLUMNS[id].label),
    [
      "Overall RIP",
      "Financial RIP",
      "Collector Appeal",
      "Typical Opening",
      "Model Break-Even",
      "Market Price",
      "Chance to Beat Cost",
      "Top Chase Market Value",
    ]
  );
});

/* ------------------------------------------------------- the data contract --- */

test("each column reads its authoritative field and derives nothing new", () => {
  assert.equal(readSortValue(ALPHA, "overall"), 100, "Overall RIP is overallRipV9.relativeScore");
  assert.equal(readSortValue(ALPHA, "financial"), 100, "Financial RIP is financialRipV3.relativeScore");
  assert.equal(readSortValue(ALPHA, "typicalOpening"), 9.5, "Typical Opening is the published median_value");
  assert.equal(readSortValue(ALPHA, "modelBreakEven"), 9.8, "Model Break-Even is the unchanged published mean_value");
  assert.equal(readSortValue(ALPHA, "marketPrice"), 100.5, "Market price is the published pack_cost");
  assert.equal(readSortValue(ALPHA, "chanceToBeatCost"), 0.098, "Chance to beat cost is prob_profit");
  assert.equal(readSortValue(ALPHA, "topChase"), 9, "Top Chase sorting is canonical chase market value");
  // Average Loss is the simulation's conditional statistic, lifted verbatim.
  assert.equal(readAverageLoss(ALPHA), 9.5, "Average Loss is expected_loss_when_losing");
  assert.equal(readTypicalOpening(ALPHA), 9.5);
  assert.equal(readModelBreakEven(ALPHA), 9.8);
});

/* ------------------------------------------- Average Loss When Losing --- */

test("Average Loss is the published conditional loss, never reconstructed from EV", () => {
  // ALPHA's unconditional gap is 90.7 and its Average Loss When Losing is 9.5.
  // Reading the authoritative field is the only way to get the second number.
  assert.equal(ALPHA.pack_cost - ALPHA.mean_value, 90.7);
  assert.equal(readAverageLoss(ALPHA), 9.5);
  assert.notEqual(readAverageLoss(ALPHA), ALPHA.pack_cost - ALPHA.mean_value);

  // The worked example from the metric definition: a $10 pack that returns $0
  // half the time and $20 the other half. EV equals cost, so the unconditional
  // gap is 0 — but the average loss when losing is a full pack cost.
  const coinFlip = { pack_cost: 10, mean_value: 10, expected_loss_when_losing: 10 };
  assert.equal(coinFlip.pack_cost - coinFlip.mean_value, 0);
  assert.equal(readAverageLoss(coinFlip), 10, "must report the conditional loss, not the zero EV gap");
});

test("a target without the published field is unavailable, with no EV-based fallback", () => {
  // Everything needed for the retired expression is present and the conditional
  // field is not. The answer must still be "unavailable".
  const noField = { pack_cost: 25, mean_value: 4 };
  assert.equal(readAverageLoss(noField), null);
  assert.equal(readSortValue(noField, "averageLoss"), null);

  const explicitNull = { pack_cost: 25, mean_value: 4, expected_loss_when_losing: null };
  assert.equal(readAverageLoss(explicitNull), null, "an explicit null is not a zero and not a cue to derive");
});

test("the camelCase alias is the same field, not a second metric", () => {
  assert.equal(readAverageLoss({ expectedLossWhenLosing: 7.25 }), 7.25);
  // The published snake_case name wins when both are present; they are two
  // spellings of one value, so this only pins the precedence.
  assert.equal(
    readAverageLoss({ expected_loss_when_losing: 7.25, expectedLossWhenLosing: 7.25 }),
    7.25
  );
});

test("Collector Appeal comes from the canonical public contract, not the retired flat column", () => {
  const withRetiredColumn = {
    ...ALPHA,
    // The CA7-era flat fields live on the same row and are ranked against a
    // different population. They must not be what this table shows.
    collector_appeal_score: 51.6977,
    collector_appeal_rank: 68,
  };
  const block = readCollectorAppealBlock(withRetiredColumn);
  assert.equal(block.publicScore, 9, "must read the canonical contract relativeScore");
  assert.equal(block.rank, 3, "must read the canonical contract rank");
  assert.notEqual(block.publicScore, 51.6977);
  assert.notEqual(block.rank, 68);
  assert.equal(readSortValue(withRetiredColumn, "collectorAppeal"), 9);
});

test("a target with no canonical Collector Appeal reports unavailable rather than a substitute", () => {
  const noContract = { ...DELTA, publicRipContractV9: undefined, collector_appeal_score: 44 };
  const block = readCollectorAppealBlock(noContract);
  assert.equal(block.available, false);
  assert.equal(block.publicScore, null, "no fallback to the retired flat score");
});

test("prob_profit is normalised the same way the cell formats it", () => {
  // Older rows publish the percentage rather than the probability; both must
  // land on one scale so the ordering is not split across two units.
  assert.equal(readSortValue({ prob_profit: 0.25 }, "chanceToBeatCost"), 0.25);
  assert.equal(readSortValue({ prob_profit: 25 }, "chanceToBeatCost"), 0.25);
});

/* --------------------------------------------------------- default ordering --- */

test("the default sort is Overall RIP descending", () => {
  assert.equal(RANKINGS_DEFAULT_SORT.column, "overall");
  assert.equal(RANKINGS_DEFAULT_SORT.direction, SORT_DESC);
});

test("the default sort returns the canonical order untouched", () => {
  const rows = sortRankingsRows(CANONICAL, RANKINGS_DEFAULT_SORT);
  assert.deepEqual(names(rows), ["alpha", "bravo", "charlie", "delta"]);
  assert.notEqual(rows, CANONICAL, "a new array is returned, the input is never sorted in place");
  assert.deepEqual(names(CANONICAL), ["alpha", "bravo", "charlie", "delta"], "the input array is unmodified");
});

/* ------------------------------------------------------- click → direction --- */

test("first click on an unselected metric sorts descending, second click ascending", () => {
  for (const columnId of RANKINGS_SORT_COLUMN_IDS) {
    // Start from a state where this column is NOT selected.
    const other = columnId === "modelBreakEven" ? "marketPrice" : "modelBreakEven";
    const first = nextSortState({ column: other, direction: SORT_ASC }, columnId);
    assert.deepEqual(first, { column: columnId, direction: SORT_DESC }, `${columnId} first click must be descending`);

    const second = nextSortState(first, columnId);
    assert.deepEqual(second, { column: columnId, direction: SORT_ASC }, `${columnId} second click must be ascending`);

    const third = nextSortState(second, columnId);
    assert.deepEqual(third, { column: columnId, direction: SORT_DESC }, `${columnId} must keep toggling`);
  }
});

test("Typical Opening uses the same sorting rule as every other metric", () => {
  const first = nextSortState({ column: "modelBreakEven", direction: SORT_DESC }, "typicalOpening");
  assert.equal(first.direction, SORT_DESC);
  const rows = sortRankingsRows(CANONICAL, first);
  // bravo 100.25, charlie 95.5, alpha 9.5 → largest average loss first.
  assert.deepEqual(names(rows), ["bravo", "charlie", "alpha", "delta"]);

  const second = nextSortState(first, "typicalOpening");
  assert.equal(second.direction, SORT_ASC);
  assert.deepEqual(names(sortRankingsRows(CANONICAL, second)), ["alpha", "charlie", "bravo", "delta"]);
});

test("aria-sort is exposed only on the active column, in the active direction", () => {
  assert.equal(ariaSortFor({ column: "modelBreakEven", direction: SORT_DESC }, "modelBreakEven"), "descending");
  assert.equal(ariaSortFor({ column: "modelBreakEven", direction: SORT_ASC }, "modelBreakEven"), "ascending");
  assert.equal(ariaSortFor({ column: "modelBreakEven", direction: SORT_ASC }, "marketPrice"), undefined);
});

/* ----------------------------------------------------------- numeric sorting --- */

test("sorting is numeric, not lexicographic, for every metric", () => {
  // Each expectation below is wrong under a string sort of the formatted value
  // ("100" < "9" < "95" / "$100.50" < "$9.80").
  const expectations = {
    overall: ["alpha", "bravo", "charlie"],
    financial: ["alpha", "charlie", "bravo"],
    collectorAppeal: ["charlie", "bravo", "alpha"],
    typicalOpening: ["bravo", "charlie", "alpha"],
    modelBreakEven: ["bravo", "charlie", "alpha"],
    marketPrice: ["alpha", "bravo", "charlie"],
    chanceToBeatCost: ["bravo", "alpha", "charlie"],
    topChase: ["bravo", "charlie", "alpha"],
  };

  for (const [columnId, expected] of Object.entries(expectations)) {
    const desc = sortRankingsRows(CANONICAL, { column: columnId, direction: SORT_DESC });
    assert.deepEqual(names(desc).slice(0, 3), expected, `${columnId} descending must order by the number`);

    const asc = sortRankingsRows(CANONICAL, { column: columnId, direction: SORT_ASC });
    assert.deepEqual(
      names(asc).slice(0, 3),
      [...expected].reverse(),
      `${columnId} ascending must be the exact reverse of descending`
    );
  }
});

test("percentage-shaped values of different digit lengths sort by magnitude", () => {
  const rows = sortRankingsRows(CANONICAL, { column: "chanceToBeatCost", direction: SORT_DESC });
  const values = rows.slice(0, 3).map((row) => readSortValue(row, "chanceToBeatCost"));
  assert.deepEqual(values, [0.741, 0.098, 0.041]);
});

/* ------------------------------------------------------------- missing data --- */

test("unavailable values sort last in BOTH directions and never become zero", () => {
  for (const columnId of RANKINGS_SORT_COLUMN_IDS) {
    for (const direction of [SORT_DESC, SORT_ASC]) {
      const rows = sortRankingsRows(CANONICAL, { column: columnId, direction });
      assert.equal(
        rows[rows.length - 1].name,
        "delta",
        `${columnId} ${direction}: the row with no value must stay last`
      );
    }
    assert.equal(readSortValue(DELTA, columnId), null, `${columnId} must stay null, never 0`);
  }
});

test("a null value is not treated as the smallest number", () => {
  const negativeEv = makeTarget({ name: "negative", overallRank: 5, meanValue: -50, packCost: 1 });
  const rows = sortRankingsRows([...CANONICAL, negativeEv], { column: "modelBreakEven", direction: SORT_ASC });
  // Ascending: the genuinely smallest number is first; the ABSENT one is last.
  assert.equal(rows[0].name, "negative");
  assert.equal(rows[rows.length - 1].name, "delta");
});

/* ------------------------------------------------------------------ stability --- */

test("tied values fall back to the canonical order, deterministically", () => {
  const tiedA = makeTarget({ name: "tied-a", overallRank: 1, meanValue: 5, packCost: 10 });
  const tiedB = makeTarget({ name: "tied-b", overallRank: 2, meanValue: 5, packCost: 10 });
  const tiedC = makeTarget({ name: "tied-c", overallRank: 3, meanValue: 5, packCost: 10 });
  const canonical = [tiedA, tiedB, tiedC];

  for (const direction of [SORT_DESC, SORT_ASC]) {
    for (let run = 0; run < 5; run += 1) {
      const rows = sortRankingsRows(canonical, { column: "modelBreakEven", direction });
      assert.deepEqual(names(rows), ["tied-a", "tied-b", "tied-c"], "ties must never reshuffle between renders");
    }
  }
});

/* ------------------------------------------------- sorting is not ranking --- */

test("sorting never mutates a target's score, rank, tier or cohort", () => {
  const before = JSON.stringify(CANONICAL);

  for (const columnId of RANKINGS_SORT_COLUMN_IDS) {
    for (const direction of [SORT_DESC, SORT_ASC]) {
      const rows = sortRankingsRows(CANONICAL, { column: columnId, direction });
      // The same object identities, only reordered — no copies, no rewrites.
      assert.equal(rows.length, CANONICAL.length);
      for (const row of rows) {
        assert.ok(CANONICAL.includes(row), "no row may be replaced by a derived object");
      }
    }
  }

  assert.equal(JSON.stringify(CANONICAL), before, "no canonical field may be written during a sort");
  // The canonical Overall RIP rank on each row is exactly what it was.
  assert.deepEqual(
    CANONICAL.map((row) => row.overallRipV9.rank),
    [1, 2, 3, 4]
  );
});

test("an unknown column falls back to the canonical order rather than throwing", () => {
  const rows = sortRankingsRows(CANONICAL, { column: "not-a-column", direction: SORT_DESC });
  assert.deepEqual(names(rows), ["alpha", "bravo", "charlie", "delta"]);
  assert.deepEqual(names(sortRankingsRows(undefined, RANKINGS_DEFAULT_SORT)), []);
});
