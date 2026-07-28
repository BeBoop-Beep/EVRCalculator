import test from "node:test";
import assert from "node:assert/strict";

import { selectPullRateRows, selectRarityTier } from "./pullRateRowsSelector.mjs";

test("selectPullRateRows flattens every group into one ordered list without dropping rows", () => {
  const rows = selectPullRateRows({
    groups: [
      {
        key: "pack_structure",
        rows: [{ rarity: "common" }, { rarity: "uncommon" }, { rarity: "rare" }, { rarity: "regular reverse" }],
      },
      {
        // Backend emits these alphabetically; the tier rank restores the
        // canonical Double -> Illustration -> Ultra -> Special -> Hyper order.
        key: "hit_rarity_model",
        rows: [
          { rarity: "double rare" },
          { rarity: "hyper rare" },
          { rarity: "illustration rare" },
          { rarity: "special illustration rare" },
          { rarity: "ultra rare" },
        ],
      },
      { key: "special_pack_rules", rows: [{ rarity: "god pack" }, { rarity: "demi god pack" }] },
    ],
    rows: [],
  });

  assert.deepEqual(
    rows.map((entry) => entry.row.rarity),
    [
      "common",
      "uncommon",
      "rare",
      "regular reverse",
      "double rare",
      "illustration rare",
      "ultra rare",
      "special illustration rare",
      "hyper rare",
      "god pack",
      "demi god pack",
    ]
  );
  assert.equal(new Set(rows.map((entry) => entry.key)).size, rows.length, "row keys must be unique");
});

test("selectPullRateRows passes canonical numeric fields through untouched", () => {
  const source = {
    group: "hit_rarity_model",
    rarity: "hyper rare",
    cardCount: 6,
    expectedCardsPerPack: 0.0128,
    rarityOddsDenominator: 78,
    specificCardOddsDenominator: 468,
    notes: "Specific-card odds sourced from set config PULL_RATE_MAPPING.",
  };

  const [entry] = selectPullRateRows({ groups: [{ key: "hit_rarity_model", rows: [source] }], rows: [] });

  // Card pool is preserved on the row (still consumed elsewhere) even though
  // the condensed table does not present it.
  assert.equal(entry.row.cardCount, 6);
  assert.equal(entry.row.expectedCardsPerPack, 0.0128);
  assert.equal(entry.row.rarityOddsDenominator, 78);
  assert.equal(entry.row.specificCardOddsDenominator, 468);
  assert.equal(entry.row.notes, source.notes);
});

test("selectPullRateRows carries the enclosing group onto rows that omit it", () => {
  const [entry] = selectPullRateRows({
    groups: [{ key: "special_pack_rules", rows: [{ rarity: "god pack", rarityOddsDenominator: 2000 }] }],
    rows: [],
  });

  assert.equal(entry.row.group, "special_pack_rules", "formatPullFrequency branches on the row's group");
  assert.equal(entry.groupKey, "special_pack_rules");
});

test("selectPullRateRows preserves payload order inside a tier and tolerates junk", () => {
  const rows = selectPullRateRows({
    groups: [{ key: "pack_structure", rows: [{ rarity: "uncommon" }, null, { rarity: "common" }, "nope"] }],
    rows: [],
  });

  assert.deepEqual(rows.map((entry) => entry.row.rarity), ["uncommon", "common"]);
});

test("selectPullRateRows falls back to the flat rows shape and empty payloads", () => {
  assert.equal(selectPullRateRows({ groups: [], rows: [{ rarity: "Rare" }] }).length, 1);
  for (const empty of [null, undefined, {}, { groups: [], rows: [] }]) {
    assert.deepEqual(selectPullRateRows(empty), []);
  }
});

test("selectRarityTier buckets unknown rarities by their group, never inventing a rarity", () => {
  assert.equal(selectRarityTier("Common", "pack_structure"), 1);
  assert.equal(selectRarityTier("REGULAR_REVERSE", "pack_structure"), 2);
  assert.equal(selectRarityTier("special illustration rare", "hit_rarity_model"), 6);
  // Unknown standard hit sorts with the other standard hits...
  assert.equal(selectRarityTier("shiny ultra rare", "hit_rarity_model"), 3);
  // ...and an unknown special-pack slot sorts last.
  assert.equal(selectRarityTier("mythic pack", "special_pack_rules"), 8);
});
