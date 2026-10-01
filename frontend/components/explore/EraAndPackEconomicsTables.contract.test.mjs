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
const unifiedTable = read("./BenchmarkEntityScoreTable.jsx");
const lazy = read("./RankingsLazyClient.jsx");
const squash = (source) => source.replace(/\s+/g, " ").replace(/\( /g, "(").replace(/ \)/g, ")").replace(/\[ /g, "[").replace(/ \]/g, "]").replace(/, ?\)/g, ")").replace(/, ?\]/g, "]");
const setPack = read("./SetPackMetrics.jsx");
const eraEconomics = read("./OpeningEconomicsEras.jsx");
const overallEconomics = read("./OpeningEconomicsOverall.jsx");
const setRankings = read("./ExploreTableClient.jsx");
const shell = read("./AnalyticsTableShell.jsx");
const css = read("./explore.module.css");

const eraContract = {
  methodologyVersion: "era_set_strength_v1_equal_set_mean_of_set_rip_v1",
  cohortSize: 2,
  eras: [
    { eraId: "mega", eraName: "Mega Evolution", score: 61.749256, rank: 1, tier: "C", modeledSetCount: 6, strongestSet: { setName: "Pitch Black" } },
    { eraId: "sv", eraName: "Scarlet & Violet", score: 45.673312, rank: 2, tier: "D", modeledSetCount: 16, strongestSet: { setName: "Temporal Forces" } },
  ],
};

// RECONCILED (B2). OLD: asserted the retired Era Set Strength wiring (page passed
// eraSetStrength to ProductFamilyRankingsClient / <EraRankings contract=...>).
// WHY OBSOLETE: Rankings now loads Era rows from the public headlines endpoint in
// RankingsLazyClient and EraRankings consumes `scorecards`.
test("Explore normalization still transports two authoritative Era rows and the live Era path reads headlines", () => {
  const normalized = normaliseRipStatisticsPayload({ targets: [], eraSetStrengthV1: eraContract });
  const rows = eraStrengthRows(normalized.eraSetStrengthV1);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].rank, 1);
  assert.equal(displayScore(rows[0].score / 10), "6.2 / 10");
  assert.equal(rows[0].tier, "C");
  assert.equal(rows[0].strongestSet.setName, "Pitch Black");
  assert.equal(displayScore(rows[1].score / 10), "4.6 / 10");
  assert.ok(page.includes("<RankingsLazyClient"));
  assert.ok(lazy.includes('readPublicRankingsHeadlines("era"'));
  assert.ok(lazy.includes("scorecards={visibleEraState.scorecards}"));
});

// RECONCILED (B2). OLD: Era Set Strength table (canonicalRows, "Era Set Strength",
// Tier, Strongest Set, Set Strength Range). WHY OBSOLETE: replaced by the unified
// Era score table. NEW: shell + shared table + the approved column set, failing
// closed when scorecards are absent.
test("EraRankings uses the Rankings table shell, the unified table, and fails closed without rows", () => {
  assert.ok(eraRankings.includes("Era RIP Score unavailable"));
  assert.ok(eraRankings.includes("!Array.isArray(scorecards.rows)"));
  assert.ok(eraRankings.includes("<AnalyticsTableShell"));
  assert.ok(eraRankings.includes("<BenchmarkEntityScoreTable"));
  assert.ok(eraRankings.includes("showModeledSets"));
  assert.ok(unifiedTable.includes("className={styles.table}"));
  assert.ok(unifiedTable.includes("styles.analyticsTableHead"));
  assert.ok(unifiedTable.includes("className={styles.row}"));
  assert.ok(unifiedTable.includes("Modeled Sets"));
  const model = read("./unifiedScoreTableModel.mjs");
  for (const label of ["RIP Score", "Financial", "Collector Appeal", "Chase"]) assert.ok(model.includes(`label: "${label}"`));
  for (const retired of ["Era Set Strength", "Strongest Set", "Set Strength Range"]) assert.ok(!eraRankings.includes(retired) && !unifiedTable.includes(retired));
});

test("Set Pack Economics expansion uses exact product rows in the parent grid", () => {
  assert.ok(setPack.includes("expandedSetId"));
  assert.ok(setPack.includes("<Fragment key={row.setId}>") );
  assert.ok(setPack.includes("<ProductRow"));
  assert.ok(!setPack.includes("<FamilyRow"));
  assert.ok(!setPack.includes("colSpan"));
  assert.ok(setPack.includes("aria-expanded={expanded}"));
  assert.ok(setPack.includes("`pack-products-${row.setId}`"));
  assert.ok(!setPack.includes("<details"));
});

test("Set Pack Economics has an explicit fixed-layout width contract", () => {
  assert.ok(setPack.includes("<colgroup>"));
  assert.ok(setPack.includes("styles.colPackEconomicsIdentity"));
  assert.ok(setPack.includes("styles.colPackEconomicsMetric"));
  assert.match(css, /\.colPackEconomicsIdentity\s*\{\s*width:\s*17rem/);
  assert.ok(!setPack.includes('className="min-w-52"'));
});

test("family classification remains available internally while Set expansion is exact-SKU only", () => {
  const families = ["booster_box", "booster_bundle", "elite_trainer_box", "loose_booster_pack", "pokemon_center_elite_trainer_box", "sleeved_booster_pack"];
  const fixture = families.map((family) => ({ family, productSkuCount: 1 }));
  const rendered = orderSetPackFamilies(fixture);
  assert.equal(rendered.length, 6);
  assert.deepEqual(rendered.map((row) => row.family), ["loose_booster_pack", "sleeved_booster_pack", "booster_bundle", "elite_trainer_box", "pokemon_center_elite_trainer_box", "booster_box"]);
  assert.deepEqual(rendered.map((row) => displaySetPackFamily(row.family)), ["Loose Booster Pack", "Sleeved Booster Pack", "Booster Bundle", "Elite Trainer Box", "Pokémon Center ETB", "Booster Box"]);
  assert.ok(setPack.includes("(row.products || []).map((product"));
  assert.ok(!/\.slice\(\s*0\s*,/.test(setPack));
  assert.ok(setPack.includes("data-pack-product-row={product.sealedProductId}"));
  assert.ok(setPack.includes("data-pack-product-mobile={product.sealedProductId}"));
  assert.ok(!setPack.includes("data-pack-family-row"));
  assert.ok(!setPack.includes("data-pack-family-mobile"));
});

test("Pack Economics keeps canonical aggregates, search, sorting and explicit Set RIP authority", () => {
  assert.ok(setPack.includes("filterPackEconomicsSets(contract?.sets, query, eraFilter)"));
  assert.ok(setPack.includes("AnalyticsTableShell"));
  assert.ok(setPack.includes("Search Sets…"));
  assert.ok(setPack.includes("row.era?.eraName"));
  assert.ok(setPack.includes('useState({ key: entitled ? "modeledReturnOnSpend" : "setName"'));
  assert.ok(!setPack.includes("Typical Opening"));
});

test("Era Pack Economics uses the same shared table language", () => {
  assert.ok(eraEconomics.includes("className={styles.table}"));
  assert.ok(eraEconomics.includes("styles.analyticsTableHead"));
  assert.ok(eraEconomics.includes("className={styles.row}"));
});

test("active Era Pack Economics omits retired Typical metrics", () => {
  for (const source of [overallEconomics, eraEconomics, setPack]) {
    assert.doesNotMatch(source, /Typical Opening|Typical Retention/);
  }
});

// RECONCILED (B2). OLD: page/client date plumbing of the retired Explore client and
// the Era Set Strength header tokens. NEW: the live page hands the opening-economics
// market date to RankingsLazyClient; Era scores render in the shared shell.
test("all four Era and Set lenses share the analytics shell and authoritative date contract", () => {
  for (const source of [eraRankings, eraEconomics, setPack]) assert.ok(source.includes("<AnalyticsTableShell"));
  assert.ok(setRankings.includes("styles.analyticsTableShell"));
  assert.ok(setRankings.includes("styles.analyticsToolbar"));
  assert.ok(shell.includes("data-analytics-table-shell"));
  assert.ok(shell.includes("set-glass-surface"));
  assert.ok(page.includes("openingEconomics?.marketDate"));
  assert.ok(page.includes("rankingsMarketDate={rankingsMarketDate}"));
  for (const token of ["Best Eras to Rip Right Now", "Search Eras…", "Select an era to view its modeled sets."]) assert.ok(eraRankings.includes(token));
  for (const token of ["Pack Economics by Era", "Search eras...", "Select an era for the full Pack Economics breakdown."]) assert.ok(eraEconomics.includes(token));
  for (const token of ["Pack Economics by Set", "Search Sets…"]) assert.ok(setPack.includes(token));
});

// RECONCILED (B2). OLD: asserted these strings in the retired ProductFamilyRankingsClient.
// NEW: the live lens tabs are in RankingsLazyClient / SetRankingsHub.
test("Rankings and Pack Economics reuse Product-family pill primitives", () => {
  const hub = read("./SetRankingsHub.jsx");
  assert.ok(lazy.includes("data-analysis-lens-tabs"));
  for (const source of [lazy, hub]) {
    assert.ok(source.includes("styles.productFamilyTab"));
    assert.ok(source.includes("styles.productFamilyTabActive"));
  }
});

test("top-level Era and Set entry resets to Rankings without breaking economics drilldown", () => {
  assert.ok(lazy.includes('const [eraLens, setEraLens] = useState("rankings")'));
  assert.ok(lazy.includes('if (next === "eras") setEraLens("rankings")'));
  assert.ok(lazy.includes('if (next === "sets") { setSetEntryView("ripScore")'));
  assert.ok(lazy.includes('setSetEntryView("packEconomics")'));
  assert.ok(lazy.includes("onSelectEra={(era) => {") || lazy.includes("onSelectEra={(era) =>"));
  assert.ok(lazy.includes("setSelectedEra(era?.eraName || null)"));
});

// RECONCILED (B2). OLD: SetRankingsHub returned null for Basic users and the retired
// client forwarded the flag. NEW: the hub swaps the paid contract for the public
// preview and SetPackMetrics locks every protected cell via `entitled`.
test("Set Pack Economics entitlement treats anonymous and unpaid accounts as Basic and Premium inherits Plus", () => {
  const fixtures = [null, { id: "signed-in-basic", index_plan: null }, { id: "plus", index_plan: "plus" }, { id: "premium", index_plan: "premium" }];
  assert.deepEqual(fixtures.map((user) => resolveRankingsPlanAccess(user).canViewRankingsIntelligence), [false, false, true, true]);
  const hub = read("./SetRankingsHub.jsx");
  assert.ok(lazy.includes("canViewRankingsIntelligence={canViewRankingsIntelligence}"));
  assert.ok(squash(hub).includes("canViewRankingsIntelligence ? await readPackEconomics"));
  assert.ok(hub.includes(": await readPublicPackEconomicsPreview"));
  assert.ok(hub.includes("entitled={canViewRankingsIntelligence}"));
  assert.ok(read("./setRankingViews.mjs").includes('value: "packEconomics", label: "Pack Economics", requiredPlan: INDEX_PLAN_PLUS'));
  assert.ok(setPack.includes("<LockedMetric />"));
  assert.ok(!setPack.includes("isAuthenticated"));
  assert.ok(!setPack.includes("index_plan"));
});

test("Era Pack Economics applies the same Plus entitlement matrix without rendering Basic values", () => {
  const fixtures = [null, { id: "signed-in-basic", index_plan: null }, { id: "plus", index_plan: "plus" }, { id: "premium", index_plan: "premium" }];
  assert.deepEqual(fixtures.map((user) => resolveRankingsPlanAccess(user).canViewRankingsIntelligence), [false, false, true, true]);
  assert.ok(lazy.includes("<OpeningEconomicsEras"));
  assert.ok(lazy.includes("canViewRankingsIntelligence={canViewRankingsIntelligence}"));
  assert.ok(squash(eraEconomics).includes('const PUBLIC_ERA_COLUMN_KEYS = new Set(["eraName", "setCount", "productSkuCount", "meanPackCost"])'));
  assert.ok(squash(eraEconomics).includes("<PremiumMetricLock />"));
  assert.ok(eraEconomics.includes("Index Plus required for full Pack Economics"));
  assert.ok(!eraEconomics.includes("isAuthenticated"));
  assert.ok(!eraEconomics.includes("index_plan"));
});

// RECONCILED (B2). OLD: the Set hub returned null for Basic users. NEW: Basic sees the
// public preview (no protected values to sort by) and Era Economics still refuses
// protected sort columns.
test("Basic Pack Economics cannot sort by hidden Set or Era intelligence", () => {
  assert.ok(read("./SetRankingsHub.jsx").includes(": await readPublicPackEconomicsPreview"));
  assert.ok(squash(eraEconomics).includes('canViewRankingsIntelligence ? DEFAULT_ERA_SORT : { key: "eraName", direction: "asc" }'));
  assert.match(squash(eraEconomics), /if \(!canViewRankingsIntelligence && column && !PUBLIC_ERA_COLUMN_KEYS\.has\(column\.key\)\) \{\s*onUnlockProductRip\?\.\(\);\s*return;/);
});

// RECONCILED (B2). OLD: single-line `COLUMNS.map((column) => <col` match; the source is
// now formatted across lines with per-column widths. Behavior unchanged.
test("Era baseline shares one renderer, one colgroup and identical column geometry", () => {
  const compact = squash(eraEconomics);
  assert.equal((eraEconomics.match(/const COLUMNS =/g) || []).length, 1);
  assert.ok(eraEconomics.includes("function EraEconomicsCell"));
  assert.ok(eraEconomics.includes("data-era-economics-colgroup"));
  assert.ok(compact.includes("COLUMNS.map((column) => (<col"));
  assert.ok(compact.includes("COLUMNS.map((column) => (<EraEconomicsCell") || compact.includes("COLUMNS.map((column) => <EraEconomicsCell"));
  assert.ok(eraEconomics.includes("column.secondary && cells[column.secondary]"));
  assert.ok(!eraEconomics.includes("<tfoot"));
  assert.ok(eraEconomics.includes("styles.eraGlobalBaselineRow"));
  assert.ok(eraEconomics.indexOf("data-era-baseline-row") < eraEconomics.indexOf("</tbody>"));
  assert.ok(eraEconomics.includes("styles.eraEconomicsCell"));
  assert.equal((css.match(/\.eraGlobalBaselineRow > td,/g) || []).length, 1);
  assert.match(css, /\.eraGlobalBaselineRow > th\[scope="row"\] \{\s*border-top: 1px solid var\(--ex-line-strong\);/);
  assert.ok(!/baseline[^\n]*(translateX|margin-left|padding-right)/.test(eraEconomics));
});

// RECONCILED (B2). OLD: EraRankings itself owned the <thead>. NEW: the unified score
// table owns it; the no-extra-colour guarantee now covers that shared table.
test("Era and Set analytics add no table-specific color material", () => {
  for (const source of [unifiedTable, eraEconomics, setPack]) {
    assert.ok(source.includes("styles.analyticsTableHead"));
    assert.ok(!/<thead[^>]*(background|bg-\[)/.test(source));
  }
  assert.ok(shell.includes("styles.surface"));
  assert.ok(shell.includes("styles.divider"));
  assert.ok(shell.includes("styles.analyticsToolbar"));
});
