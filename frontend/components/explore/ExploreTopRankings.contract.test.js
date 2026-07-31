/**
 * Top Rankings leaderboard contract (Explore refinement Phase 2).
 *
 * The module ranks sets by the canonical CHECKLIST SET VALUE already enriched
 * onto the Explore targets payload. These tests exist to keep it a
 * presentation surface: authoritative fields only, no derived or filled-in
 * values, no extra request.
 */

const fs = require("fs");
const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");

const componentPath = path.resolve(__dirname, "ExploreTopRankings.jsx");

function readComponent() {
  return fs.readFileSync(componentPath, "utf8");
}

test("Top Rankings accepts targets and a loadError prop", () => {
  const source = readComponent();
  assert.ok(
    source.includes("export default function ExploreTopRankings({ targets = [], loadError = false }) {"),
    "the module must take the already-fetched targets and the shared load-error flag"
  );
});

test("the ladder reads the canonical checklist set value fields", () => {
  const source = readComponent();
  assert.ok(
    source.includes("target?.checklistSetValue ?? target?.checklist_set_value"),
    "the value must come from the canonical checklistSetValue field (either spelling)"
  );
  assert.ok(
    source.includes("target?.checklistSetValueAsOf ?? target?.checklist_set_value_as_of"),
    "the as-of date must come from the same enrichment"
  );
  assert.ok(
    source.includes("checklistSetValuePricedCardCount") && source.includes("checklistSetValueTotalCardCount"),
    "priced-card coverage must be read so partial pricing can be disclosed"
  );
});

test("no score, rank, or tier is invented for the set value ladder", () => {
  const source = readComponent();
  // Set value has no backend rank or tier; the position shown is this list's
  // own order and nothing may pretend otherwise.
  for (const invented of ["getRankForMode", "getTierForMode", "getRelativeScoreForMode", "RANK_CONFIG", "getTierTone"]) {
    assert.ok(!source.includes(invented), `${invented} must not back a set-value ladder`);
  }
  assert.ok(
    source.includes(".map((row, index) => ({ ...row, position: index + 1 }))"),
    "the position must be an explicit presentational index"
  );
  assert.ok(
    source.includes('aria-label="Sets ordered by checklist set value, highest first"'),
    "the list must state what its order means"
  );
});

test("sets without a checklist value are omitted, never shown as zero", () => {
  const source = readComponent();
  assert.ok(
    source.includes("filter((row) => row.value !== null)"),
    "a set with no checklist value must be dropped from the ladder"
  );
  assert.ok(source.includes('UNAVAILABLE_LABEL = "Unavailable"'), "an explicit Unavailable label must exist");
  assert.ok(source.includes("value === null ? UNAVAILABLE_LABEL"), "a null value must never render as a number");
});

test("the ladder orders by value descending with a stable name tie-break", () => {
  const source = readComponent();
  assert.ok(source.includes("return right.value - left.value;"), "highest set value first");
  assert.ok(source.includes("localeCompare"), "ties must break on name so the order is stable");
});

test("rows disclose stale pricing inline and coverage in the row detail", () => {
  const source = readComponent();
  assert.ok(
    source.includes("Boolean(asOf && latestAsOf && asOf < latestAsOf)"),
    "a row priced before the newest snapshot date must be flagged on its own row"
  );
  assert.ok(source.includes('<span className="sr-only">priced </span>'), "the stale date must be labelled for assistive tech");
  // Partial pricing is common rather than exceptional, so it is disclosed in
  // the row's detail text instead of printing a ratio on most rows.
  assert.ok(
    source.includes("`${coverage.priced} of ${coverage.total} cards priced`"),
    "priced-card coverage must still be disclosed in the row detail"
  );
  assert.ok(source.includes("title={detail}"), "the detail text must be reachable from the row");
});

test("rows carry the documented hierarchy: position, logo, name, value", () => {
  const source = readComponent();
  assert.ok(source.includes("<LadderLogo target={target} name={name} />"), "each row shows the set's compact visual identity");
  assert.ok(source.includes("{name}</span>"), "each row shows the set name");
  assert.ok(source.includes("setValueFormatter.format(value)"), "each row shows the set value as currency");
});

// A set-value ranking row belongs on Overview, where the set value and its
// trend live. It previously deep-linked to the Insights RIP-score section,
// which is a different metric from the one the row is ranked by.
test("a ranking row opens the set's Overview tab", () => {
  const source = readComponent();
  assert.ok(
    source.includes('buildTcgSetHrefFromTarget(target, { tab: "overview" })'),
    "rows must link to the Overview tab"
  );
  assert.ok(!source.includes('tab: "insights"'), "rows must not link to Insights");
  assert.ok(!source.includes('section: "rip-score"'), "rows must not deep-link to the RIP score section");
});

test("row navigation still goes through the shared routing helper and set slug", () => {
  const source = readComponent();
  assert.ok(
    source.includes('import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting"'),
    "routing must stay in the shared helper, not be hand-built in this component"
  );
  assert.ok(!source.includes("/TCGs/Pokemon/Sets/"), "the base route must not be hardcoded here");

  // Prove the produced href shape end to end against the real helper.
  const routingSource = fs.readFileSync(
    path.resolve(__dirname, "..", "..", "lib", "explore", "ripStatisticsRouting.js"),
    "utf8"
  );
  assert.ok(routingSource.includes("export function buildTcgSetHrefFromTarget"), "the helper must still exist");
});

test("rows stay navigable and quiet: one link per row, no per-row card border", () => {
  const source = readComponent();
  assert.ok(source.includes("buildTcgSetHrefFromTarget(target"), "rows must navigate to the set page");
  assert.ok(source.includes("className={styles.ladderRow}"), "rows must use the shared separator-based ladder treatment");
  const css = fs.readFileSync(path.resolve(__dirname, "explore.module.css"), "utf8");
  const ladderStart = css.indexOf(".ladderRow {");
  const ladderBlock = css.slice(ladderStart, css.indexOf("}", ladderStart));
  assert.ok(!/[^-]border:/.test(ladderBlock), "ladder rows must use a separator, not a full border");
  assert.ok(ladderBlock.includes("border-bottom"), "ladder rows must be separated by a subtle divider");
});

test("mobile Top Rankings shows ten rows before the compact More control expands the remainder", () => {
  const source = readComponent();
  assert.ok(source.includes("MOBILE_PREVIEW_LIMIT = 10"), "the preview limit must be explicit");
  assert.ok(source.includes("visibleMobileRows"), "the visible slice must be separate from the full ladder");
  assert.ok(source.includes("hiddenMobileCount"), "the remaining rows must be counted");
  assert.ok(source.includes('showAllMobileRows ? "Show less" : "More"'), "the toggle must expand and collapse");
  assert.ok(source.includes('className="mt-auto hidden items-center justify-between'), "the footer action must stay desktop-only");
});

test("Top Rankings has its own empty and error states so it cannot collapse the row", () => {
  const source = readComponent();
  assert.ok(source.includes("ladder.length > 0 ? ("), "must branch on whether the ladder has rows");
  assert.ok(source.includes(") : loadError ? ("), "must have a distinct load-error branch");
  assert.ok(source.includes('role="alert"'), "the error state must be announced");
  assert.ok(source.includes("Ranked sets appear here once"), "the genuine-empty state must stay understandable");
});

test("the module adds no data request of its own", () => {
  const source = readComponent();
  assert.ok(!source.includes("fetch("), "Top Rankings must reuse the page's targets, never fetch");
  assert.ok(!source.includes("getPokemonSet"), "no client-side data loading may be introduced");
});

// Staleness is a backend selection problem. The component must keep rendering
// whatever the canonical enrichment publishes — it must never reach for a
// second source, compare snapshot windows itself, or paper over a stale date.
test("staleness is never resolved in the component", () => {
  const source = readComponent();
  for (const windowToken of ["30d", "365d", "window_key", "windowKey", "latest_market_date"]) {
    assert.ok(!source.includes(windowToken), `the component must not reason about ${windowToken}`);
  }
  assert.ok(
    source.includes("readSetValue(target)") && source.includes("readSetValueAsOf(target)"),
    "the value and its as-of date must both come from the enriched target"
  );
  // The stale-date indicator must survive: it truthfully reports a row that
  // received an older snapshot and is not a workaround to be deleted.
  assert.ok(
    source.includes("Boolean(asOf && latestAsOf && asOf < latestAsOf)"),
    "the stale-date indicator must remain"
  );
});
