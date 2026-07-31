import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (rel) => fs.readFileSync(path.resolve(here, rel), "utf8").replace(/\r\n/g, "\n");

const client = read("RipStatisticsPageClient.jsx");
const mobileHero = read("../pokemon/set-page/PokemonSetHero/PokemonSetMobileHero.jsx");

const between = (source, startToken, endToken) => {
  const start = source.indexOf(startToken);
  assert.ok(start >= 0, `missing ${startToken}`);
  const end = source.indexOf(endToken, start);
  assert.ok(end > start, `missing ${endToken} after ${startToken}`);
  return source.slice(start, end);
};

// ===========================================================================
// B. Unified sticky set control area (below 1200px)
// ===========================================================================

const stickyBlock = between(client, "data-set-detail-sticky-tabs", "</div>\n                <section");

test("the set picker and the local tabs live in one sticky block below 1200px", () => {
  assert.ok(stickyBlock.includes("data-set-sticky-picker"), "the picker renders inside the sticky block");
  assert.ok(stickyBlock.includes("<PokemonSetMobileHero"), "the picker is the mobile hero");
  assert.ok(stickyBlock.includes("<SectionViewTabs"), "the local tabs render inside the same sticky block");
  assert.ok(
    stickyBlock.indexOf("data-set-sticky-picker") < stickyBlock.indexOf("<SectionViewTabs"),
    "the picker sits above the tabs"
  );
});

test("the unified block is the element that is actually pinned", () => {
  const css = read("../../app/styles/globals.css");
  const mobileBlock = css.slice(css.indexOf("@media (max-width: 1199.98px) {"));
  const stickyRule = mobileBlock.slice(mobileBlock.indexOf(".set-detail-sticky-tabs {"));
  assert.ok(stickyRule.includes("position: sticky"), "the block is sticky below desktop");
  assert.ok(stickyRule.includes("top: var(--app-header-offset"), "it pins below the unchanged global header");
});

test("the picker reads as the top row of the block, not a second stacked card", () => {
  assert.ok(
    stickyBlock.includes('surfaceClassName="rounded-none border-0 bg-transparent'),
    "the nested hero drops its own border and radius"
  );
  assert.ok(mobileHero.includes("surfaceClassName"), "the hero accepts the flattening class");
  assert.ok(
    mobileHero.includes("rounded-xl border px-3 py-2.5"),
    "the standalone hero surface is unchanged for any other caller"
  );
});

test("the picker row still carries logo, name, era and a dropdown affordance", () => {
  assert.ok(mobileHero.includes("identity.hasLogo") && mobileHero.includes("identity.logoUrl"), "set logo");
  assert.ok(mobileHero.includes("identity.name"), "set name");
  assert.ok(mobileHero.includes("identity.era"), "set era");
  assert.ok(mobileHero.includes('aria-haspopup="listbox"'), "dropdown affordance");
  assert.ok(mobileHero.includes('"Switch set"'), "switch-set label text is preserved");
});

test("there is exactly one picker owner and one local tabs tree", () => {
  assert.equal(
    (client.match(/<PokemonSetMobileHero/g) || []).length,
    1,
    "the mobile hero is rendered once"
  );
  assert.equal(
    (client.match(/data-set-mobile-picker/g) || []).length,
    0,
    "the mobile picker trigger is owned by the hero component, not duplicated in the page"
  );
  assert.equal(
    (client.match(/value={setDetailTab}/g) || []).length,
    1,
    "there is a single local tabs tree"
  );
  // Ownership is still a single width reading, so only one picker is operable.
  assert.ok(client.includes("isPickerOwner={!isDesktopHeroComposition}"));
  assert.equal(
    (client.match(/const \[heroSetPickerOpen, setHeroSetPickerOpen\] = useState/g) || []).length,
    1
  );
});

test("desktop composition is untouched by the sticky unification", () => {
  assert.ok(
    client.includes('data-set-sticky-picker data-set-picker className="relative z-30 desk:hidden">'),
    "the sticky picker row is hidden at desktop"
  );
  assert.ok(
    client.includes("relative min-h-[88px] overflow-visible rounded-t-xl border max-desk:hidden desk:order-1"),
    "the desktop context header keeps its own composition and reading order"
  );
});

// ===========================================================================
// D. Top Chase — sparkline integrated into the row below 1200px
// ===========================================================================

const compactSparkline = between(client, "function CompactSparkline(", "function normalizeSetValueHistoryPoints(");

test("the Top Chase sparkline loses its container box below 1200px", () => {
  assert.ok(
    compactSparkline.includes(
      'className="h-full w-full overflow-visible rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/42 max-desk:rounded-none max-desk:border-0 max-desk:bg-transparent"'
    ),
    "the plot drops its border, radius and fill below desktop"
  );
  assert.ok(
    compactSparkline.includes("max-desk:rounded-none max-desk:border-0 max-desk:bg-transparent\", className]"),
    "the empty state matches so the row never flips between framed and frameless"
  );
});

test("desktop keeps the framed sparkline", () => {
  assert.ok(
    compactSparkline.includes("rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/42"),
    "the desktop frame classes are still present and unprefixed"
  );
});

test("the Top Chase row keeps every field and its interactions", () => {
  const row = between(client, "function TopMarketCardRow(", "function InlinePanelSkeleton(");
  assert.ok(row.includes("#{index + 1}"), "rank");
  assert.ok(row.includes("imageUrl"), "card image");
  assert.ok(row.includes("{name}"), "name");
  assert.ok(row.includes("rarity"), "rarity");
  assert.ok(row.includes("price"), "price");
  assert.ok(row.includes("displayDelta"), "movement");
  assert.ok(row.includes("<CompactSparkline"), "sparkline");
  assert.ok(row.includes("sparklinePoints"), "sparkline data");
  // The plot stays outside the navigation link so scrubbing never triggers nav.
  assert.ok(
    row.indexOf("</NavigationRegion>") < row.indexOf("<CompactSparkline"),
    "the sparkline must stay outside the row link"
  );
});

test("Top Chase still defaults to five rows with all ten reachable", () => {
  const chaseModule = between(client, "function TopChaseCardsModule(", "function MoversTickerItemChip");
  assert.ok(chaseModule.includes("showAllChaseCards ? 10 : TOP_CHASE_MOBILE_PREVIEW_LIMIT"));
});

// ===========================================================================
// E. Decision Signals — compact structured list below 1200px
// ===========================================================================

const compactList = between(client, "function DecisionSignalsCompactList(", "function DecisionSignalRow(");
const signalsCard = between(client, "function DecisionSignalsCard(", "// A Profit / Safety / Stability card.");

test("below 1200px Decision Signals renders the compact list, not the stacked rows", () => {
  assert.ok(
    signalsCard.includes('<div className="desk:hidden">\n        <DecisionSignalsCompactList'),
    "the compact list is the mobile/tablet tree"
  );
  assert.ok(
    signalsCard.includes('<div className="hidden desk:block">'),
    "the previous row presentation is desktop-only"
  );
  assert.ok(
    signalsCard.indexOf('<div className="desk:hidden">') < signalsCard.indexOf('<div className="hidden desk:block">'),
    "the compact list is the first tree"
  );
});

test("the compact row exposes exactly the four scan fields in order", () => {
  assert.ok(
    compactList.includes("grid-cols-[minmax(0,1fr)_3rem_3.75rem_2.5rem]"),
    "a stable signal / score / tier / rank grid"
  );
  assert.ok(compactList.includes("{signal.label}"), "signal name");
  assert.ok(compactList.includes('{signal.scoreText || "—"}'), "score");
  assert.ok(compactList.includes("rank={signal.rankTier}"), "tier badge");
  assert.ok(compactList.includes("`#${rankLabel}`"), "rank");
  const header = between(compactList, 'aria-hidden="true"', "</div>");
  assert.ok(header.includes("Score") && header.includes("Tier") && header.includes("Rank"));
});

test("scores, tiers and ranks are read straight off the shared view model", () => {
  // No recomputation, no re-rounding, no re-ranking in the mobile tree: the
  // same fields the desktop rows render.
  assert.ok(compactList.includes("toNumber(signal.rankValue)"), "rank comes from rankValue, as on desktop");
  assert.ok(compactList.includes("Math.round(parsedRank)"), "same rank rounding as the desktop row");
  assert.ok(!/score\s*[*+/-]/.test(compactList), "no arithmetic is applied to the score");
  assert.ok(!compactList.includes("sort("), "row order is not re-sorted");
  assert.ok(!compactList.includes("|| 0"), "no fake zero is substituted for a missing value");
});

test("Decision Signals renders three explicit groups with stable row feeds", () => {
  assert.ok(compactList.includes('groupLabel("OVERALL RIP")'));
  assert.ok(compactList.includes('groupLabel("CORE")'));
  assert.ok(compactList.includes('groupLabel("ALSO TRACKED")'));
  assert.ok(compactList.includes("overallRows.map(renderRow)"));
  assert.ok(compactList.includes("pillarRows.map(renderRow)"));
  assert.ok(compactList.includes("trackedRows.map(renderRow)"));
  // The card still assembles both groups from the same selectors as before.
  assert.ok(signalsCard.includes("selectDecisionSignals({ pillarSignals, summary, requestTimeout }).rows"));
  assert.ok(signalsCard.includes("SET_INTELLIGENCE_LENSES.map"));
});

test("interpretations are preserved but only one is visible at a time", () => {
  assert.ok(
    compactList.includes("selectedSignal.detailSummary || selectedSignal.summary"),
    "the full existing interpretation is displayed, not a rewritten one"
  );
  // Exactly one shared detail region, rendered once outside the row loop.
  assert.equal(
    (compactList.match(/data-decision-signal-detail/g) || []).length,
    1,
    "there is exactly one shared detail region"
  );
  assert.ok(
    !between(compactList, "const renderRow =", "const groupLabel =").includes("detailSummary"),
    "no interpretation is printed inside a row"
  );
});

test("selecting a row reveals its interpretation and re-selecting collapses it", () => {
  assert.ok(
    compactList.includes("setSelectedLabel((previous) => (previous === signal.label ? null : signal.label))"),
    "selection toggles and replaces, so a second row swaps the detail"
  );
  assert.ok(compactList.includes("allRows.find((signal) => signal.label === selectedLabel)"));
  assert.ok(
    compactList.includes("Select a signal to see what it means for this set."),
    "the default is no selection, with a clear affordance"
  );
});

test("row selection is accessible by keyboard and not by colour alone", () => {
  assert.ok(compactList.includes('type="button"'), "a real button gives Enter and Space for free");
  assert.ok(compactList.includes("aria-expanded={isSelected}"));
  assert.ok(compactList.includes("aria-controls={detailRegionId}"));
  assert.ok(compactList.includes('aria-live="polite"'), "detail changes are announced");
  assert.ok(compactList.includes("focus-visible:ring-2"), "focus stays visible");
  assert.ok(compactList.includes("border-l-[var(--accent)]"), "selection also carries a non-colour edge marker");
  assert.ok(compactList.includes("min-h-14"), "rows remain comfortably touch-safe");
  assert.ok(compactList.includes('<span className="sr-only">{`Rank ${rankLabel}`}</span>'), "rank has a full label");
});

test("Decision Signals still fetches nothing", () => {
  for (const token of ["fetch(", "useEffect", "await "]) {
    assert.ok(!compactList.includes(token), `the compact list must not ${token.trim()}`);
  }
});

// ===========================================================================
// Cross-cutting: no duplicated charts, no new requests
// ===========================================================================

test("the refinement pass introduces no duplicate chart mounts", () => {
  const packValue = read("PackValueHistoryChart.jsx");
  assert.equal((packValue.match(/<ResponsiveContainer/g) || []).length, 1);
  const setValueChart = between(client, "function SetValueLineChart(", "function SetValueTrendCard");
  assert.equal((setValueChart.match(/<ResponsiveContainer/g) || []).length, 1);
  assert.equal((client.match(/<CompactSparkline/g) || []).length, 1);
});

test("the refinement pass introduces no new request paths", () => {
  // The mobile trees are presentation-only: the same four slim module fetches
  // as before, no mobile-only endpoint, no extra call sites.
  for (const [fetcher, expected] of [
    ["getPokemonSetOverview(", 1],
    ["getPokemonSetTopChase(", 1],
    ["getPokemonSetMarketMovers(", 1],
  ]) {
    assert.equal(
      (client.match(new RegExp(fetcher.replace(/[()]/g, "\\$&"), "g")) || []).length,
      expected,
      `${fetcher} must still have exactly ${expected} call site`
    );
  }
  assert.ok(!compactList.includes("/api/"), "the compact list issues no request");
  assert.ok(!stickyBlock.includes("/api/"), "the sticky control area issues no request");
});
