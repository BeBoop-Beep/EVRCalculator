import assert from "node:assert/strict";
import test from "node:test";

import { normalizePokemonSetPullRatesPayload } from "./pokemonSetPullRatesClient.js";

function makePullRatesPayload(overrides = {}) {
  return {
    set: { id: "set-1", name: "Prismatic Evolutions", slug: "prismaticEvolutions" },
    pullRates: {
      groups: [
        {
          key: "pack_structure",
          label: "Pack Structure",
          rows: [
            { rarity: "Common", cardCount: 60, expectedCardsPerPack: 4, specificCardOddsDenominator: 15 },
          ],
        },
      ],
      rows: [],
    },
    packPaths: [],
    rarityBuckets: [],
    assumptions: {},
    sources: [],
    meta: { source: "pokemon_set_page_snapshot_latest", updatedAt: "2026-06-30T00:00:00+00:00", warnings: [] },
    ...overrides,
  };
}

test("normalizePokemonSetPullRatesPayload returns set, pullRateAssumptions groups/rows, and meta", () => {
  const normalized = normalizePokemonSetPullRatesPayload(makePullRatesPayload());

  assert.deepEqual(normalized.set, { id: "set-1", name: "Prismatic Evolutions", slug: "prismaticEvolutions" });
  assert.equal(normalized.pullRateAssumptions.groups.length, 1);
  assert.equal(normalized.pullRateAssumptions.groups[0].key, "pack_structure");
  assert.equal(normalized.pullRateAssumptions.groups[0].rows[0].rarity, "Common");
  assert.equal(normalized.pullRateAssumptions.groups[0].rows[0].cardCount, 60);
  assert.equal(normalized.pullRateAssumptions.groups[0].rows[0].expectedCardsPerPack, 4);
  assert.equal(normalized.pullRateAssumptions.groups[0].rows[0].specificCardOddsDenominator, 15);
  assert.deepEqual(normalized.packPaths, []);
  assert.deepEqual(normalized.rarityBuckets, []);
  assert.deepEqual(normalized.assumptions, {});
  assert.deepEqual(normalized.sources, []);
  assert.equal(normalized.meta.source, "pokemon_set_page_snapshot_latest");
});

test("normalizePokemonSetPullRatesPayload normalizes flat rows (no groups) fallback shape", () => {
  const payload = makePullRatesPayload({
    pullRates: {
      rows: [{ rarity: "Rare", card_count: 12, rarity_odds_denominator: 8 }],
    },
  });

  const normalized = normalizePokemonSetPullRatesPayload(payload);

  assert.equal(normalized.pullRateAssumptions.groups.length, 0);
  assert.equal(normalized.pullRateAssumptions.rows.length, 1);
  assert.equal(normalized.pullRateAssumptions.rows[0].cardCount, 12);
  assert.equal(normalized.pullRateAssumptions.rows[0].rarityOddsDenominator, 8);
});

test("normalizePokemonSetPullRatesPayload tolerates a missing/empty pullRates block", () => {
  const normalized = normalizePokemonSetPullRatesPayload(makePullRatesPayload({ pullRates: null }));

  assert.equal(normalized.pullRateAssumptions, null);
});

test("normalizePokemonSetPullRatesPayload is defensive against a completely empty payload", () => {
  const normalized = normalizePokemonSetPullRatesPayload({});

  assert.deepEqual(normalized.set, { id: null, name: null, slug: null });
  assert.equal(normalized.pullRateAssumptions, null);
  assert.deepEqual(normalized.packPaths, []);
  assert.deepEqual(normalized.rarityBuckets, []);
  assert.deepEqual(normalized.assumptions, {});
  assert.deepEqual(normalized.sources, []);
  assert.deepEqual(normalized.meta, { warnings: [] });
});
