import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { normaliseRipStatisticsPayload } from "../../lib/explore/ripStatisticsNormalizer.mjs";
import { eraStrengthRows, displayScore } from "./eraSetStrengthSelector.mjs";
import { displaySetPackFamily, orderSetPackFamilies } from "./setPackFamilyPresentation.mjs";
import { resolveRankingsPlanAccess } from "../../lib/access/indexPlanAccess.mjs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const page = read("../../app/Explore/page.js");
const client = read("./ProductFamilyRankingsClient.jsx");
const eraRankings = read("./EraRankings.jsx");
const setPack = read("./SetPackMetrics.jsx");
const eraEconomics = read("./OpeningEconomicsEras.jsx");
const setRankings = read("./ExploreTableClient.jsx");
const shell = read("./AnalyticsTableShell.jsx");

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
  assert.ok(eraRankings.includes("canonicalRows.length === 0"));
  assert.ok(eraRankings.includes("data-era-rankings-unavailable"));
  assert.ok(eraRankings.includes("Era Set Strength could not be loaded"));
  assert.ok(eraRankings.includes("className={styles.table}"));
  assert.ok(eraRankings.includes("styles.analyticsTableHead"));
  assert.ok(eraRankings.includes("className={styles.row}"));
  for (const label of ["Rank", "Era", "Era Set Strength", "Tier", "Sets", "Strongest Set", "Set Strength Range"]) assert.ok(eraRankings.includes(label));
});

test("Set Pack Economics expansion is a sibling full-width table row", () => {
  assert.ok(setPack.includes("expandedSetId"));
  assert.ok(setPack.includes("<Fragment key={row.setId}>") );
  assert.ok(setPack.includes('className="family-detail-row"'));
  assert.ok(setPack.includes("<td colSpan={TOTAL_COLUMN_COUNT}"));
  assert.ok(setPack.includes("aria-expanded={expanded}"));
  assert.ok(setPack.includes("`family-economics-${row.setId}`"));
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
  assert.ok(setPack.includes("AnalyticsTableShell"));
  assert.ok(setPack.includes("Search sets..."));
  assert.ok(setPack.includes("row.eraName"));
  assert.ok(setPack.includes('canViewRankingsIntelligence ? "modeledReturn" : "packPrice"'));
  assert.ok(setPack.includes("Set RIP #{row.canonicalRank"));
  assert.ok(!setPack.includes("averageModelBreakEvenPerPack /"));
});

test("Era Pack Economics uses the same shared table language", () => {
  assert.ok(eraEconomics.includes("className={styles.table}"));
  assert.ok(eraEconomics.includes("styles.analyticsTableHead"));
  assert.ok(eraEconomics.includes("className={styles.row}"));
});

test("all four Era and Set lenses share the analytics shell and authoritative date contract", () => {
  for (const source of [eraRankings, eraEconomics, setPack]) assert.ok(source.includes("<AnalyticsTableShell"));
  assert.ok(setRankings.includes("styles.analyticsTableShell"));
  assert.ok(setRankings.includes("styles.analyticsToolbar"));
  assert.ok(shell.includes("data-analytics-table-shell"));
  assert.ok(page.includes("payload?.meta?.comparisonSnapshots?.currentMarketDate || null"));
  assert.ok(client.includes("marketDate={openingEconomics?.marketDate}"));
  for (const token of ["Best Eras to Rip Right Now", "Search eras...", "Select an era for the full RIP breakdown."]) assert.ok(eraRankings.includes(token));
  for (const token of ["Pack Economics by Era", "Search eras...", "Select an era for the full Pack Economics breakdown."]) assert.ok(eraEconomics.includes(token));
  for (const token of ["Pack Economics by Set", "Search sets..."]) assert.ok(setPack.includes(token));
});

test("Rankings and Pack Economics reuse Product-family pill primitives", () => {
  assert.ok(client.includes("data-analysis-lens-tabs"));
  assert.ok(client.includes("styles.productFamilyTab"));
  assert.ok(client.includes("styles.productFamilyTabActive"));
  assert.ok(!client.includes('ariaLabel={`${view === "eras" ? "Era" : "Set"} analysis`}'));
});

test("top-level Era and Set entry resets to Rankings without breaking economics drilldown", () => {
  assert.ok(client.includes('const [eraLens, setEraLens] = useState("rankings")'));
  assert.ok(client.includes('if (next === "eras") setEraLens("rankings")'));
  assert.ok(client.includes('if (next === "sets") setSetLens("rankings")'));
  assert.ok(client.includes('setSetLens("economics");'));
  assert.ok(client.includes('onSelectEra={(era) => {'));
  assert.ok(client.indexOf('setSetLens("economics");') < client.indexOf('setSelectedEra(era?.eraName || null);', client.indexOf('setSetLens("economics");')));
});

test("Set Pack Economics entitlement treats anonymous and unpaid accounts as Basic and Premium inherits Plus", () => {
  const fixtures = [null, { id: "signed-in-basic", index_plan: null }, { id: "plus", index_plan: "plus" }, { id: "premium", index_plan: "premium" }];
  assert.deepEqual(fixtures.map((user) => resolveRankingsPlanAccess(user).canViewRankingsIntelligence), [false, false, true, true]);
  assert.ok(client.includes("canViewRankingsIntelligence={canViewRankingsIntelligence}"));
  assert.ok(setPack.includes('const PUBLIC_COLUMN_KEYS = new Set(["products", "packPrice"])'));
  assert.ok(setPack.includes("canViewRankingsIntelligence || PUBLIC_COLUMN_KEYS.has(key)"));
  assert.ok(setPack.includes("<PremiumMetricLock />"));
  assert.ok(setPack.includes("Index Plus required for detailed Pack Economics"));
  assert.ok(setPack.includes("expanded = canViewRankingsIntelligence"));
  assert.ok(setPack.includes("expanded ? <tr"), "family values only mount for entitled expansion");
  assert.ok(!setPack.includes("isAuthenticated"));
  assert.ok(!setPack.includes("index_plan"));
});

test("Era Pack Economics applies the same Plus entitlement matrix without rendering Basic values", () => {
  const fixtures = [null, { id: "signed-in-basic", index_plan: null }, { id: "plus", index_plan: "plus" }, { id: "premium", index_plan: "premium" }];
  assert.deepEqual(fixtures.map((user) => resolveRankingsPlanAccess(user).canViewRankingsIntelligence), [false, false, true, true]);
  assert.ok(client.includes("<OpeningEconomicsEras"));
  assert.ok(client.includes("canViewRankingsIntelligence={canViewRankingsIntelligence}"));
  assert.ok(eraEconomics.includes('const PUBLIC_ERA_COLUMN_KEYS = new Set(["eraName", "setCount", "productSkuCount", "meanPackCost"])'));
  assert.ok(eraEconomics.includes("locked ? <PremiumMetricLock />"));
  assert.ok(eraEconomics.includes("Index Plus required for full Pack Economics"));
  assert.ok(!eraEconomics.includes("isAuthenticated"));
  assert.ok(!eraEconomics.includes("index_plan"));
});

test("Basic Pack Economics cannot sort by hidden Set or Era intelligence", () => {
  assert.ok(setPack.includes('canViewRankingsIntelligence ? "modeledReturn" : "packPrice"'));
  assert.match(setPack, /if \(!canViewRankingsIntelligence && !PUBLIC_COLUMN_KEYS\.has\(key\)\) \{\s*onUnlockProductRip\?\.\(\);\s*return;/);
  assert.ok(eraEconomics.includes('canViewRankingsIntelligence ? DEFAULT_ERA_SORT : { key: "eraName", direction: "asc" }'));
  assert.match(eraEconomics, /if \(!canViewRankingsIntelligence && column && !PUBLIC_ERA_COLUMN_KEYS\.has\(column\.key\)\) \{\s*onUnlockProductRip\?\.\(\);\s*return;/);
});

test("Era baseline shares one renderer, one colgroup and identical column geometry", () => {
  assert.equal((eraEconomics.match(/const COLUMNS =/g) || []).length, 1);
  assert.ok(eraEconomics.includes("function EraEconomicsCell"));
  assert.ok(eraEconomics.includes("data-era-economics-colgroup"));
  assert.ok(eraEconomics.includes("COLUMNS.map((column) => <col"));
  assert.ok(eraEconomics.includes("COLUMNS.map((column) => <EraEconomicsCell"));
  assert.ok(eraEconomics.includes("baseline canViewRankingsIntelligence"));
  assert.ok(eraEconomics.includes("column.secondary && cells[column.secondary]"));
  assert.ok(!/baseline[^\n]*(translateX|margin-left|padding-right)/.test(eraEconomics));
});
