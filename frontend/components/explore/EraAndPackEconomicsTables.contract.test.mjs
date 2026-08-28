import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { normaliseRipStatisticsPayload } from "../../lib/explore/ripStatisticsNormalizer.mjs";
import { eraStrengthRows, displayScore } from "./eraSetStrengthSelector.mjs";
import { displaySetPackFamily, orderSetPackFamilies } from "./setPackFamilyPresentation.mjs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const page = read("../../app/Explore/page.js");
const client = read("./ProductFamilyRankingsClient.jsx");
const eraRankings = read("./EraRankings.jsx");
const setPack = read("./SetPackMetrics.jsx");
const eraEconomics = read("./OpeningEconomicsEras.jsx");

const eraContract = {
  methodologyVersion: "era_set_strength_v1_equal_set_mean_of_set_rip_v1",
  cohortSize: 2,
  eras: [
    { eraId: "mega", eraName: "Mega Evolution", score: 61.749256, rank: 1, tier: "C", modeledSetCount: 6, strongestSet: { setName: "Pitch Black" } },
    { eraId: "sv", eraName: "Scarlet & Violet", score: 45.673312, rank: 2, tier: "D", modeledSetCount: 16, strongestSet: { setName: "Temporal Forces" } },
  ],
};

test("Explore normalization transports two authoritative Era rows into EraRankings", () => {
  const normalized = normaliseRipStatisticsPayload({ targets: [], eraSetStrengthV1: eraContract });
  const rows = eraStrengthRows(normalized.eraSetStrengthV1);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].rank, 1);
  assert.equal(displayScore(rows[0].score / 10), "6.2 / 10");
  assert.equal(rows[0].tier, "C");
  assert.equal(rows[0].strongestSet.setName, "Pitch Black");
  assert.equal(displayScore(rows[1].score / 10), "4.6 / 10");
  assert.ok(page.includes("eraSetStrength={payload?.eraSetStrengthV1}"));
  assert.ok(client.includes("<EraRankings contract={eraSetStrength}"));
});

test("EraRankings uses the Rankings table shell and fails closed without rows", () => {
  assert.ok(eraRankings.includes("rows.length === 0"));
  assert.ok(eraRankings.includes("data-era-rankings-unavailable"));
  assert.ok(eraRankings.includes("Era Set Strength could not be loaded"));
  assert.ok(eraRankings.includes("className={styles.table}"));
  assert.ok(eraRankings.includes("className={styles.head}"));
  assert.ok(eraRankings.includes("className={styles.row}"));
  for (const label of ["Rank", "Era", "Era Set Strength", "Tier", "Sets", "Strongest Set", "Set Strength Range"]) assert.ok(eraRankings.includes(label));
});

test("Set Pack Economics expansion is a sibling full-width table row", () => {
  assert.ok(setPack.includes("expandedSetId"));
  assert.ok(setPack.includes("<Fragment key={row.setId}>") );
  assert.ok(setPack.includes('className="family-detail-row"'));
  assert.ok(setPack.includes("<td colSpan={TOTAL_COLUMN_COUNT}"));
  assert.ok(setPack.includes("aria-expanded={expanded}"));
  assert.ok(setPack.includes("aria-controls={`family-economics-${row.setId}`}"));
  assert.ok(!setPack.includes("<details"));
  assert.ok(!setPack.includes("<th className=\"min-w-64 text-left\"><Identity"));
});

test("Pitch Black's six represented families are ordered and never truncated", () => {
  const families = ["booster_box", "booster_bundle", "elite_trainer_box", "loose_booster_pack", "pokemon_center_elite_trainer_box", "sleeved_booster_pack"];
  const fixture = families.map((family) => ({ family, productSkuCount: 1 }));
  const rendered = orderSetPackFamilies(fixture);
  assert.equal(rendered.length, 6);
  assert.deepEqual(rendered.map((row) => row.family), ["loose_booster_pack", "sleeved_booster_pack", "booster_bundle", "elite_trainer_box", "pokemon_center_elite_trainer_box", "booster_box"]);
  assert.deepEqual(rendered.map((row) => displaySetPackFamily(row.family)), ["Loose Booster Pack", "Sleeved Booster Pack", "Booster Bundle", "Elite Trainer Box", "Pokémon Center ETB", "Booster Box"]);
  assert.ok(setPack.includes("families.map((row)"));
  assert.ok(!/\.slice\(\s*0\s*,/.test(setPack));
  assert.ok(setPack.includes("data-family-economics-row={row.family}"));
  assert.ok(setPack.includes("data-family-economics-mobile-row={row.family}"));
});

test("Pack Economics keeps canonical aggregates, search, sorting and explicit Set RIP authority", () => {
  assert.ok(setPack.includes("mergeSetEconomics(sets, targets)"));
  assert.ok(setPack.includes("TableSearchInput"));
  assert.ok(setPack.includes("Search sets..."));
  assert.ok(setPack.includes("row.eraName"));
  assert.ok(setPack.includes('key: "modeledReturn", direction: "desc"'));
  assert.ok(setPack.includes("Set RIP #{row.canonicalRank"));
  assert.ok(!setPack.includes("averageModelBreakEvenPerPack /"));
});

test("Era Pack Economics uses the same shared table language", () => {
  assert.ok(eraEconomics.includes("className={styles.table}"));
  assert.ok(eraEconomics.includes("className={styles.head}"));
  assert.ok(eraEconomics.includes("className={styles.row}"));
});
