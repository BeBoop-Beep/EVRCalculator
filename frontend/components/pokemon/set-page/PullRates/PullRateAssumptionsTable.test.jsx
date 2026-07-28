import test from "node:test";
import assert from "node:assert/strict";
import React, { act } from "react";
import TestRenderer from "react-test-renderer";

import PullRateAssumptionsTable from "./PullRateAssumptionsTable.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// Mirrors the real normalized payload shape: pack_structure keeps its canonical
// common -> uncommon -> rare -> regular reverse order, hit_rarity_model arrives
// ALPHABETICALLY (the backend emits `for rarity_key in sorted(hit_rarity_keys)`),
// and special_pack_rules holds the set-specific slots.
function makeAssumptions(overrides = {}) {
  return {
    groups: [
      {
        key: "pack_structure",
        label: "Pack Structure",
        rows: [
          { group: "pack_structure", rarity: "common", cardCount: 81, expectedCardsPerPack: 4, specificCardOddsDenominator: 20 },
          { group: "pack_structure", rarity: "uncommon", cardCount: 45, expectedCardsPerPack: 3, specificCardOddsDenominator: 15 },
          { group: "pack_structure", rarity: "rare", cardCount: 20, expectedCardsPerPack: 0.75, specificCardOddsDenominator: 27 },
          { group: "pack_structure", rarity: "regular reverse", cardCount: 176, expectedCardsPerPack: 1.87, specificCardOddsDenominator: 94 },
        ],
      },
      {
        key: "hit_rarity_model",
        label: "Hit Rarity Model",
        rows: [
          { group: "hit_rarity_model", rarity: "double rare", cardCount: 18, rarityOddsDenominator: 7, specificCardOddsDenominator: 124 },
          { group: "hit_rarity_model", rarity: "hyper rare", cardCount: 6, rarityOddsDenominator: 78, specificCardOddsDenominator: 468 },
          { group: "hit_rarity_model", rarity: "illustration rare", cardCount: 36, rarityOddsDenominator: 13, specificCardOddsDenominator: 473 },
          { group: "hit_rarity_model", rarity: "special illustration rare", cardCount: 15, rarityOddsDenominator: 32, specificCardOddsDenominator: 468 },
          { group: "hit_rarity_model", rarity: "ultra rare", cardCount: 8, rarityOddsDenominator: 30, specificCardOddsDenominator: 240 },
        ],
      },
      {
        key: "special_pack_rules",
        label: "Special Pack Rules",
        rows: [
          { group: "special_pack_rules", rarity: "god pack", cardCount: 3, rarityOddsDenominator: 2000, specificCardOddsDenominator: 6000, slotLabel: "Special pack model" },
        ],
      },
    ],
    rows: [],
    ...overrides,
  };
}

function render(pullRateAssumptions) {
  let renderer;
  act(() => {
    renderer = TestRenderer.create(<PullRateAssumptionsTable pullRateAssumptions={pullRateAssumptions} />);
  });
  return renderer;
}

function textOf(node) {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  return textOf(node.children);
}

function headerCells(renderer) {
  return renderer.root.findAllByType("th").map((cell) => textOf(cell.props.children).trim());
}

function dataRows(renderer) {
  return renderer.root.findAllByType("tr").filter((row) => row.findAllByType("td").length > 0);
}

function bodyRows(renderer) {
  return dataRows(renderer).map((row) => row.findAllByType("td").map((cell) => textOf(cell.props.children).trim()));
}

test("the section renders exactly one table with the four condensed columns", () => {
  const renderer = render(makeAssumptions());

  const tables = renderer.root.findAllByType("table");
  assert.equal(tables.length, 1, "the condensed section must render one table shell, not one per group");

  // Exactly 4 <th> in total: one header row, no group-heading rows, no
  // repeated headers from a split layout.
  assert.deepEqual(headerCells(renderer), ["Rarity / Slot", "Card Pool", "Pull Frequency", "Specific Card Odds"]);

  assert.equal(renderer.root.findAllByType("col").length, 4, "the colgroup must size exactly four columns");
});

test("the removed summary cards, group headings, accordion, and explanatory copy are gone", () => {
  const renderer = render(makeAssumptions());
  const markup = JSON.stringify(renderer.toJSON());

  for (const removed of [
    "Tracked Rarities",
    "Chase Slot",
    "Advanced &amp; Special-Pack Odds",
    "Advanced & Special-Pack Odds",
    "PACK STRUCTURE",
    "Pack Structure",
    "HIT RARITY MODEL",
    "Hit Rarity Model",
    "Special Pack Rules",
    "Modeled rarity frequency and specific-card odds used by this simulation.",
    "These are modeled estimates, not official Pok",
    "Source references for these modeled odds",
  ]) {
    assert.ok(!markup.includes(removed), `"${removed}" must no longer render in the section`);
  }

  // "Specific Card Odds" and "Card Pool" survive ONLY as column headers —
  // never as summary metric cards.
  assert.equal(markup.split("Specific Card Odds").length - 1, 1, "Specific Card Odds must appear once, as the column header");
  assert.equal(markup.split("Card Pool").length - 1, 1, "Card Pool must appear once, as the column header");

  assert.equal(renderer.root.findAllByType("details").length, 0, "no accordion may remain");
  assert.equal(renderer.root.findAllByType("summary").length, 0, "no accordion summary may remain");
  assert.equal(renderer.root.findAllByType("svg").length, 0, "no open/close chevron may remain");
  assert.equal(renderer.root.findAllByType("button").length, 0, "no toggle control may remain");
});

test("pack-structure and advanced/special rows are visible simultaneously in canonical tier order", () => {
  const renderer = render(makeAssumptions());
  const rarities = bodyRows(renderer).map((cells) => cells[0]);

  assert.deepEqual(rarities, [
    "Common",
    "Uncommon",
    "Rare",
    "Regular Reverse",
    "Double Rare",
    "Illustration Rare",
    "Ultra Rare",
    "Special Illustration Rare",
    "Hyper Rare",
    "God Pack",
  ]);
});

test("existing normalized card-pool, pull-frequency, and specific-card-odds values render unchanged", () => {
  const renderer = render(makeAssumptions());
  const byRarity = new Map(bodyRows(renderer).map((cells) => [cells[0], cells]));

  for (const cells of bodyRows(renderer)) {
    assert.equal(cells.length, 4, "each row must render exactly the four condensed columns");
  }

  assert.deepEqual(byRarity.get("Common"), ["Common", "81", "4 per pack", "1 in 20 packs"]);
  assert.deepEqual(byRarity.get("Rare"), ["Rare", "20", "1 in 1.3 packs", "1 in 27 packs"]);
  assert.deepEqual(byRarity.get("Regular Reverse"), ["Regular Reverse", "176", "1.87 per pack", "1 in 94 packs"]);
  assert.deepEqual(byRarity.get("Double Rare"), ["Double Rare", "18", "1 in 7 packs", "1 in 124 packs"]);
  assert.deepEqual(byRarity.get("Illustration Rare"), ["Illustration Rare", "36", "1 in 13 packs", "1 in 473 packs"]);
  assert.deepEqual(byRarity.get("Special Illustration Rare"), ["Special Illustration Rare", "15", "1 in 32 packs", "1 in 468 packs"]);
  assert.deepEqual(byRarity.get("Hyper Rare"), ["Hyper Rare", "6", "1 in 78 packs", "1 in 468 packs"]);
  assert.deepEqual(byRarity.get("God Pack"), ["God Pack", "3", "1 in 2,000 packs", "1 in 6,000 packs"]);
});

test("card pool reads the canonical payload field and is never derived from the other columns", () => {
  // A pool that could not be back-derived from odds/frequency proves the cell
  // is a passthrough of the normalized value, not a client-side computation.
  const renderer = render({
    groups: [
      {
        key: "hit_rarity_model",
        rows: [{ group: "hit_rarity_model", rarity: "ultra rare", cardCount: 7, rarityOddsDenominator: 30, specificCardOddsDenominator: 999 }],
      },
    ],
    rows: [],
  });

  assert.deepEqual(bodyRows(renderer), [["Ultra Rare", "7", "1 in 30 packs", "1 in 999 packs"]]);

  // snake_case and the eligible_card_count alias are accepted too.
  const snakeCase = render({
    groups: [],
    rows: [
      { rarity: "Rare", card_count: 12, rarity_odds_denominator: 8 },
      { rarity: "Ultra Rare", eligible_card_count: 5, rarity_odds_denominator: 30 },
    ],
  });
  assert.deepEqual(
    bodyRows(snakeCase).map((cells) => cells[1]),
    ["12", "5"]
  );
});

test("missing card-pool values render the unavailable convention, never a misleading zero", () => {
  const renderer = render({
    groups: [
      {
        key: "hit_rarity_model",
        rows: [
          { group: "hit_rarity_model", rarity: "double rare", cardCount: null, rarityOddsDenominator: 7, specificCardOddsDenominator: 84 },
          { group: "hit_rarity_model", rarity: "illustration rare", rarityOddsDenominator: 13, specificCardOddsDenominator: 473 },
          { group: "hit_rarity_model", rarity: "ultra rare", cardCount: "", rarityOddsDenominator: 30 },
          { group: "hit_rarity_model", rarity: "hyper rare", cardCount: "not-a-number", rarityOddsDenominator: 78 },
        ],
      },
    ],
    rows: [],
  });

  const pools = bodyRows(renderer).map((cells) => cells[1]);
  assert.deepEqual(pools, ["—", "—", "—", "—"], "null, absent, empty-string, and NaN pools must all render as —");
  assert.ok(!pools.includes("0"), "a missing pool must never be shown as 0");

  // An explicit zero in the canonical payload is a real value and is shown.
  const explicitZero = render({
    groups: [],
    rows: [{ rarity: "Promo", cardCount: 0, rarityOddsDenominator: 10 }],
  });
  assert.equal(bodyRows(explicitZero)[0][1], "0");
});

test("card pool stays visible and readable on the compact layout", () => {
  const renderer = render(makeAssumptions());

  const [rarityCol, poolCol] = renderer.root.findAllByType("col").map((col) => col.props.className);
  // Card Pool is the narrowest column; the rarity name keeps the most room.
  const width = (className) => Number(/w-\[(\d+)%\]/.exec(className)[1]);
  assert.ok(width(poolCol) < width(rarityCol), "Card Pool must be the narrowest column, rarity the widest");

  for (const row of dataRows(renderer)) {
    const [rarityCell, poolCell] = row.findAllByType("td");
    // No responsive utility may hide any column on small screens.
    for (const cell of row.findAllByType("td")) {
      assert.ok(!/\bhidden\b/.test(cell.props.className), "no column may be hidden on small screens");
    }
    // Pool digits stay on one line; long rarity names wrap instead of forcing
    // the page to scroll sideways.
    assert.ok(poolCell.props.className.includes("whitespace-nowrap"));
    assert.ok(rarityCell.props.className.includes("break-words"));
    assert.ok(rarityCell.props.className.includes("whitespace-normal"));
  }

  const shell = renderer.root.findAllByType("div")[0];
  assert.ok(shell.props.className.includes("overflow-x-auto"), "the table must scroll inside its own shell, never the page");
  assert.ok(shell.props.className.includes("max-w-full"));
});

test("specific-card odds keep the yellow accent emphasis", () => {
  const renderer = render(makeAssumptions());

  for (const row of dataRows(renderer)) {
    const oddsCell = row.findAllByType("td")[3];
    assert.ok(
      oddsCell.props.className.includes("text-[var(--accent)]"),
      "the Specific Card Odds cell must keep the accent (yellow) emphasis"
    );
  }
});

test("sets with missing optional rarity groups render safely", () => {
  const packStructureOnly = render(
    makeAssumptions({
      groups: [
        {
          key: "pack_structure",
          label: "Pack Structure",
          rows: [{ group: "pack_structure", rarity: "common", cardCount: 81, expectedCardsPerPack: 4, specificCardOddsDenominator: 20 }],
        },
        { key: "hit_rarity_model", label: "Hit Rarity Model", rows: [] },
        { key: "special_pack_rules", label: "Special Pack Rules", rows: [] },
      ],
    })
  );
  assert.equal(packStructureOnly.root.findAllByType("table").length, 1);
  assert.deepEqual(bodyRows(packStructureOnly), [["Common", "81", "4 per pack", "1 in 20 packs"]]);

  // Flat `rows` fallback (no groups at all).
  const flat = render({ groups: [], rows: [{ rarity: "Rare", card_count: 12, rarity_odds_denominator: 8 }] });
  assert.deepEqual(bodyRows(flat), [["Rare", "12", "1 in 8 packs", "—"]]);

  // Nothing available at all — a plain line, never another bordered panel.
  for (const empty of [null, undefined, {}, { groups: [], rows: [] }]) {
    const renderer = render(empty);
    assert.equal(renderer.root.findAllByType("table").length, 0);
    assert.match(textOf(renderer.toJSON().children), /Pull-rate assumptions are not available/);
  }
});

test("a set with an unrecognised rarity keeps that row without inventing tiers", () => {
  const renderer = render({
    groups: [
      {
        key: "hit_rarity_model",
        label: "Hit Rarity Model",
        rows: [
          { group: "hit_rarity_model", rarity: "hyper rare", cardCount: 6, rarityOddsDenominator: 78, specificCardOddsDenominator: 468 },
          { group: "hit_rarity_model", rarity: "shiny ultra rare", cardCount: 21, rarityOddsDenominator: 20, specificCardOddsDenominator: 120 },
        ],
      },
    ],
    rows: [],
  });

  // The unknown rarity sorts with the other standard hits (tier 3) and is
  // never dropped.
  assert.deepEqual(bodyRows(renderer).map((cells) => cells[0]), ["Shiny Ultra Rare", "Hyper Rare"]);
});
