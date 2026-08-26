import assert from "node:assert/strict";
import test from "node:test";
import {
  selectCollectorDriverSubjects,
  selectCollectorRankDrivers,
  selectFinancialRankDrivers,
} from "./ripStorySelectors.mjs";

test("financial drivers use backend component rank only", () => {
  const rows = [
    { key: "a", title: "A", rankValue: 8, cohortSize: 22 },
    { key: "b", title: "B", rankValue: 2, cohortSize: 22 },
    { key: "c", title: "C", rankValue: 15, cohortSize: 22 },
  ];
  const selected = selectFinancialRankDrivers(rows);
  assert.deepEqual(
    selected.strengths.map((row) => row.key),
    ["b", "a"],
  );
  assert.deepEqual(
    selected.drags.map((row) => row.key),
    ["c"],
  );
  assert.equal(
    selectFinancialRankDrivers([{ key: "missing" }]).available,
    false,
  );
});

test("collector drivers classify canonical cohort ranks without forcing a split", () => {
  const factor = (key, rank) => ({
    key,
    title: key,
    rank,
    cohortSize: 22,
    tier: rank < 5 ? "S" : "F",
  });
  assert.deepEqual(
    selectCollectorRankDrivers([factor("a", 1), factor("b", 4)]).strengths.map(
      (row) => row.key,
    ),
    ["a", "b"],
  );
  assert.equal(
    selectCollectorRankDrivers([factor("a", 1), factor("b", 4)]).drags.length,
    0,
  );
  assert.deepEqual(
    selectCollectorRankDrivers([factor("a", 18), factor("b", 20)]).drags.map(
      (row) => row.key,
    ),
    ["b", "a"],
  );
  const split = selectCollectorRankDrivers([factor("a", 3), factor("b", 17)]);
  assert.deepEqual([split.strengths[0].key, split.drags[0].key], ["a", "b"]);
  assert.equal(
    selectCollectorRankDrivers([factor("missing", null)]).available,
    false,
  );
});

test("collector subjects tolerate missing images and support either or both paths", () => {
  const canonical = {
    collectorAppeal: {
      topSubjects: [
        {
          subjectName: "Accessible",
          demandScore: 98.2,
          demandShare: 0.181,
          accessiblePath: { cardName: "Card A", impliedOdds: 12 },
        },
        {
          subjectName: "Elite",
          demandShare: 0.007,
          elitePath: {
            cardName: "Card B",
            imageUrl: null,
            impliedOdds: 900,
            packsFor50PercentChance: 624,
            packsFor90PercentChance: 2072,
          },
        },
        {
          subjectName: "Both",
          demandShare: 0,
          accessiblePath: { cardName: "Card C", impliedOdds: 0 },
          elitePath: { cardName: "Card D", impliedOdds: 50 },
        },
        { subjectName: "Empty" },
      ],
    },
  };
  const rows = selectCollectorDriverSubjects(canonical);
  assert.equal(rows.length, 3);
  assert.ok(rows[0].accessiblePath && !rows[0].elitePath);
  assert.ok(!rows[1].accessiblePath && rows[1].elitePath);
  assert.ok(rows[2].accessiblePath && rows[2].elitePath);
  assert.equal(
    rows[2].accessiblePath.impliedOdds,
    null,
    "zero odds never render as 1 in 0",
  );
  assert.equal(rows[0].demandShareLabel, "18%");
  assert.equal(rows[1].demandShareLabel, "<1%");
  assert.equal(rows[1].elitePath.packsFor50PercentChance, 624);
  assert.equal(rows[1].elitePath.packsFor90PercentChance, 2072);
  assert.equal(rows[2].demandShareLabel, "0%");
  assert.equal(
    rows[0].subjectDemand,
    undefined,
    "absolute demand score is not presented as a share",
  );
  assert.deepEqual(selectCollectorDriverSubjects({}), []);
});
