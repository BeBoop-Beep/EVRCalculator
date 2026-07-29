import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const clientPath = path.join(here, "RipStatisticsPageClient.jsx");
const globalsPath = path.join(here, "../../app/styles/globals.css");
const scaffoldPath = path.join(here, "../Profile/PublicProfileLocalScaffold.js");
const source = fs.readFileSync(clientPath, "utf8").replace(/\r\n/g, "\n");
const globals = fs.readFileSync(globalsPath, "utf8").replace(/\r\n/g, "\n");
const scaffold = fs.readFileSync(scaffoldPath, "utf8").replace(/\r\n/g, "\n");

function shellSource() {
  const start = source.indexOf("<div data-set-context-shell");
  const end = source.indexOf('{setDetailTab === "overview" ? (', start);
  assert.ok(start >= 0 && end > start, "persistent set shell markers must exist");
  return source.slice(start, end);
}

test("set detail removes the sidebar and uses one invariant shell on every tab", () => {
  const shell = shellSource();
  assert.ok(source.includes("desktopSidebarContent={setDetailMode ? null : desktopSidebarContent}"));
  assert.ok(source.includes("hideDesktopSidebar={setDetailMode}"));
  assert.ok(scaffold.includes("{!hideDesktopSidebar ? <aside"));
  assert.equal((source.match(/data-set-context-shell/g) || []).length, 2); // selector lookup + rendered shell
  assert.equal((source.match(/data-set-context-header/g) || []).length, 1);
  assert.ok(!source.includes("data-set-summary-surface"));
  assert.ok(!source.includes("data-set-hero-grid"));
  assert.ok(shell.includes("data-set-detail-sticky-tabs"));
});

test("context row uses the 46/27/27 identity, value, and Opening RIP structure", () => {
  const shell = shellSource();
  assert.ok(shell.includes("md:grid-cols-[minmax(0,46fr)_minmax(0,27fr)_minmax(0,27fr)]"));
  assert.ok(shell.includes("data-compact-set-picker"));
  assert.ok(shell.includes("gap-4 px-4 py-2.5 sm:gap-6"));
  assert.ok(shell.includes("md:gap-7"));
  assert.ok(shell.includes("h-14 w-24"));
  assert.ok(shell.includes("sm:h-16 sm:w-28"));
  assert.ok(shell.includes("max-h-14 w-auto max-w-24 object-contain opacity-95"));
  assert.ok(shell.includes("set-context-identity"));
  assert.ok(shell.includes("text-lg font-semibold"));
  assert.ok(shell.includes("md:text-xl"));
  assert.ok(shell.includes("text-xs font-medium leading-tight"));
  assert.ok(shell.includes("selectedName"));
  assert.ok(shell.includes("selectedTarget?.era"));
  assert.ok(shell.includes("Set Value"));
  assert.ok(shell.includes("{setContextRipLabel}"), "the RIP column is labelled from the canonical selection");
  assert.ok(shell.includes("displayedTopScore"));
  assert.ok(shell.includes("setContextRipTier"));
  assert.ok(shell.includes("setContextRipRank"));
  assert.ok(shell.includes("recommendationBadge"));
  // All three derive from the same `heroScoreSelection` the Insights breakdown
  // renders, so the card cannot show a different mode's tier or rank.
  for (const derivation of [
    "const setContextRipTier = String(heroScoreSelection.tier",
    "const setContextRipRank = toNumber(heroScoreSelection.rank)",
    "const setContextRipCohort = toNumber(heroScoreSelection.cohortSize)",
  ]) {
    assert.ok(source.includes(derivation), `missing shared-selection derivation: ${derivation}`);
  }
});

test("the title-card RIP summary shares the detailed breakdown's tier presentation", () => {
  const shell = shellSource();

  // Tier and verdict are outlined pills in the same shape language as the
  // breakdown's RankBadge / InterpretationBadge (rounded-full, 1px border).
  // The RANK is not: it is a position rather than a judgement, and a third
  // outlined chip made the compact card read as three competing badges.
  for (const marker of ["data-set-context-rip-tier", "data-set-context-rip-rank", "data-set-context-rip-verdict"]) {
    assert.equal((shell.match(new RegExp(marker, "g")) || []).length, 1, `${marker} must render once`);
  }
  assert.ok(shell.includes("style={setContextRipPresentation.tierPill}"));
  assert.ok(shell.includes("style={setContextRipPresentation.verdictPill}"));
  assert.ok(!shell.includes("style={setContextRipPresentation.rankPill}"), "the rank must not carry a pill style");
  assert.equal((shell.match(/rounded-full border px-2 py-0\.5/g) || []).length, 2, "only the tier and verdict are pills");

  // The rank element itself carries no bubble: no border, no rounding, no fill.
  const rankStart = shell.indexOf("data-set-context-rip-rank");
  const rankTag = shell.slice(rankStart, shell.indexOf(">", shell.indexOf("title=", rankStart)));
  assert.ok(!/rounded/.test(rankTag), "the rank must not be a rounded chip");
  assert.ok(!/\bborder/.test(rankTag), "the rank must not draw a border");
  assert.ok(!/\bbg-/.test(rankTag), "the rank must not carry a background fill");

  // One shared semantic source, keyed on the active tier — no hard-coded tier
  // colour and no second mapping for the title card.
  assert.ok(
    source.includes("const setContextRipPresentation = getRipTierPresentation({"),
    "the title card must read the shared tier presentation helper"
  );
  assert.ok(!/style=\{\{[^}]*color: *"#|rgba\(134, ?239, ?172/.test(shell), "no tier colour may be hard-coded in the shell");

  // The score itself stays the neutral focal point.
  assert.ok(shell.includes('<span className="text-sm font-semibold leading-tight tabular-nums text-[var(--text-primary)]">{displayedTopScore}</span>'));

  // Tier and rank are readable text, not colour-only signals. The rank reads
  // "Rank #20" — the cohort denominator lives in its tooltip, not on the row.
  assert.ok(shell.includes("{setContextRipTier} Tier"));
  assert.ok(shell.includes("Rank #{Math.round(setContextRipRank)}"));
  assert.ok(
    !/>\s*Rank #\{Math\.round\(setContextRipRank\)\} of /.test(shell),
    'the compact summary must not render "of N"'
  );

  // Metadata wraps instead of relying on a fixed measure.
  assert.ok(shell.includes("flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1"));
  assert.ok(!/data-set-context-rip-\w+[\s\S]{0,240}\bw-\[/.test(shell), "pills must not take a fixed width");
});

test("the title-card label names the metric it is actually showing", () => {
  // Both modes take the label from the canonical selection. The previous
  // version special-cased RIP Score into a hard-coded "Opening RIP" eyebrow,
  // which gave the same canonical score two different user-facing names
  // depending on which surface you were looking at.
  assert.ok(
    source.includes("const setContextRipLabel = heroScoreSelection.label;"),
    "the title card must take its label from the canonical selection in BOTH modes"
  );
  assert.ok(!/["'>]Opening RIP["'<]/.test(source), "the legacy label must not survive anywhere");
  assert.ok(shellSource().includes('<p className="set-context-eyebrow">{setContextRipLabel}</p>'));
});

test("persistent shell contains only concise context and deep-link actions", () => {
  const shell = shellSource();
  assert.ok(shell.includes("onClick={handleViewSetValueTrend}"));
  assert.ok(shell.includes("View trend"));
  assert.ok(shell.includes('tab: "insights", section: "rip-score", targetId: "set-detail-rip-score"'));
  assert.ok(shell.includes("View verdict"));
  assert.equal((shell.match(/set-context-action/g) || []).length, 2);
  assert.ok(!shell.includes("<CompactSparkline"));
  assert.ok(!shell.includes("headerDecisionMetrics"));
  assert.ok(!shell.includes("Opening Outlook"));
  assert.ok(!shell.includes("<RipScoreModeToggle"));
});

test("set switching remains keyboard and pointer accessible in the persistent identity", () => {
  const shell = shellSource();
  assert.ok(shell.includes('aria-haspopup="listbox"'));
  assert.ok(shell.includes('aria-controls="compact-set-picker-list"'));
  assert.ok(shell.includes("switcherTargets.map("));
  assert.ok(shell.includes("onMouseEnter={() => handleTargetPrefetch"));
  assert.ok(shell.includes("onFocus={() => handleTargetPrefetch"));
  assert.ok(shell.includes("handleHeroSetSelect"));
  assert.ok(shell.includes("onKeyDown={handleSetPickerKeyDown}"));
  assert.ok(source.includes('event.target.closest?.("[data-set-picker]")'));
  const selectionStart = source.indexOf("const handleHeroSetSelect = (target) => {");
  const selectionEnd = source.indexOf("const handleSetPickerKeyDown", selectionStart);
  const selection = source.slice(selectionStart, selectionEnd);
  assert.ok(selection.includes('handleTargetIdChange(String(target?.target_id || ""));'));
  assert.ok(
    selection.indexOf("handleTargetIdChange") < selection.indexOf("setHeroSetPickerOpen(false)"),
    "canonical route navigation must be accepted before the menu closes"
  );
});

test("context row and tabs stick together below global navigation", () => {
  assert.match(globals, /\.set-detail-context-shell[\s\S]+position: sticky;[\s\S]+top: var\(--app-header-offset, 64px\);[\s\S]+z-index: 40;/);
  assert.match(globals, /\[data-set-context-header\][\s\S]+position: relative;[\s\S]+z-index: 2;[\s\S]+overflow: visible;/);
  assert.match(globals, /\.set-detail-sticky-tabs[\s\S]+position: relative;[\s\S]+z-index: 1;/);
  assert.ok(shellSource().includes("set-context-premium"));
  assert.ok(globals.includes("--set-context-bg:"));
  assert.ok(globals.includes("--set-context-wash:"));
  assert.match(globals, /\.set-context-premium \{[\s\S]+background: var\(--set-context-bg\);[\s\S]+box-shadow:/);
  assert.match(globals, /\.set-detail-context-shell::before \{[\s\S]+background: var\(--set-context-wash\);/);
  assert.ok(shellSource().includes("z-50 max-h-56"));
  assert.ok(source.includes('"[data-set-context-shell]"'));
  assert.ok(source.includes("headerOffset + subNavHeight + pinnedHeight + 8"));

  // Below 1200px the hero is ordinary content and only the tab bar pins, so the
  // offset helper measures the tab bar rather than the whole shell — measuring
  // the shell there would over-scroll every anchor by the full hero height.
  // Desktop keeps measuring the shell, which is what the assertions above lock.
  assert.ok(source.includes('window.matchMedia("(min-width: 1200px)")'));
  assert.ok(
    source.includes('isDesktopComposition ? "[data-set-context-shell]" : "[data-set-detail-sticky-tabs]"'),
    "the helper measures whichever element is actually pinned at the current width"
  );
  assert.match(
    globals,
    /@media \(max-width: 1199\.98px\)[\s\S]+\.set-detail-context-shell \{[\s\S]+display: contents;/,
    "the shell stops generating a box below the desktop boundary, so the tabs stick page-wide"
  );
});

test("set-page content uses shared standard and dense glass surfaces without changing the sticky context card", () => {
  const shell = shellSource();
  assert.ok(source.includes("set-detail-glass-scope"));
  assert.ok(source.includes('"set-glass-surface w-full max-w-full min-w-0"'));
  // Cards is deliberately NOT a glass panel: a surface there was the first
  // ancestor blocking the ambient set artwork behind the grid. The section is
  // a transparent layout region (like #set-detail-overview) and only its
  // compact controls strip carries a surface.
  assert.ok(
    source.includes('<section id="set-detail-cards" data-cards-section className="scroll-mt-24 space-y-4 md:scroll-mt-28">'),
    "the Cards section must stay a transparent layout region"
  );
  assert.ok(
    !/id="set-detail-cards"[^>]*set-glass-surface/.test(source),
    "no glass surface may be reintroduced on the Cards section itself"
  );
  assert.ok(
    source.includes('<div data-cards-toolbar className="set-glass-surface space-y-3 rounded-2xl border p-3 md:p-4">'),
    "the Cards controls must keep their own compact translucent panel"
  );
  assert.ok(globals.includes("--set-glass-bg: rgba(8, 17, 31, 0.40);"));
  assert.ok(globals.includes("--set-glass-bg-dense: rgba(8, 17, 31, 0.52);"));
  assert.ok(globals.includes("--set-glass-border: rgba(145, 174, 212, 0.14);"));
  assert.ok(globals.includes("--set-glass-blur: 4px;"));
  assert.ok(globals.includes("--set-glass-blur-dense: 6px;"));
  assert.ok(globals.includes("--set-glass-inner-bg: rgba(8, 17, 31, 0.14);"));
  assert.ok(globals.includes("--set-glass-inner-bg-dense: rgba(8, 17, 31, 0.20);"));
  assert.ok(source.includes("set-glass-inner overflow-visible rounded-xl"));
  assert.ok(source.includes("set-glass-inner mb-4 flex flex-col"));
  assert.match(
    globals,
    /\.set-detail-glass-scope \.set-glass-surface,[\s\S]+-webkit-backdrop-filter: blur\(var\(--set-glass-blur\)\);[\s\S]+backdrop-filter: blur\(var\(--set-glass-blur\)\);/
  );
  assert.match(
    globals,
    /\.set-detail-glass-scope \.set-glass-surface-dense \{[\s\S]+backdrop-filter: blur\(var\(--set-glass-blur-dense\)\);/
  );
  assert.ok(!shell.includes("set-glass-surface"), "the persistent set-context title card must remain unchanged");
});

// The ambient set artwork must reach the eye through the whole Cards stack:
// section -> grid wrapper -> card tile -> metadata. Any opaque or frosted
// surface on an ancestor makes the transparent tiles reveal that panel instead
// of the artwork, so each layer is pinned here.
function cardsSectionSource() {
  const start = source.indexOf('<section id="set-detail-cards"');
  const end = source.indexOf('{setDetailTab === "pull-rates" ? (', start);
  assert.ok(start >= 0 && end > start, "the Cards section markers must exist");
  return source.slice(start, end);
}

test("the Cards transparency stack: only the controls carry a surface, never the grid", () => {
  const cards = cardsSectionSource();

  // 1. The section itself paints nothing.
  const sectionTag = cards.slice(0, cards.indexOf(">") + 1);
  assert.ok(!/set-glass|bg-|backdrop-blur/.test(sectionTag), `the Cards section tag must paint nothing: ${sectionTag}`);

  // 2. Exactly one controls panel, and it holds the tabs, search, and the
  //    sort/rarity/direction/timeframe/metric/count strip.
  assert.equal((cards.match(/data-cards-toolbar/g) || []).length, 1, "there must be exactly one controls panel");
  const toolbarStart = cards.indexOf("<div data-cards-toolbar");
  const toolbar = cards.slice(toolbarStart, cards.indexOf('{cardsSubTab === "checklist" ? (\n                      <div className="min-w-0">'));
  for (const control of [
    "<SectionViewTabs",
    'placeholder="Search cards by name"',
    'aria-label="Sort cards by"',
    "availableCardRarities.map",
    'aria-label="Movement timeframe"',
    'aria-label="Rank movement by"',
    "cards\n",
  ]) {
    assert.ok(toolbar.includes(control), `the controls panel must contain ${control.trim()}`);
  }

  // 3. The controls strip is not a nested bordered panel inside that panel.
  assert.ok(
    toolbar.includes('<div className="flex flex-wrap items-end gap-3">'),
    "the filter strip must sit flat inside the controls panel, not in its own bordered box"
  );
  assert.ok(
    !toolbar.includes('bg-[var(--surface-page)]/20'),
    "the old nested filter-strip surface must be gone"
  );

  // 4. The grid wrapper and the grid itself paint nothing.
  const gridStart = cards.indexOf('<div className="grid grid-cols-2');
  assert.ok(gridStart > 0, "the card grid must exist");
  const gridTag = cards.slice(gridStart, cards.indexOf(">", gridStart) + 1);
  assert.ok(!/set-glass|bg-|backdrop-blur/.test(gridTag), `the grid must paint nothing: ${gridTag}`);
  assert.ok(cards.includes('<div className="min-w-0">'), "the grid wrapper stays a bare layout div");

  // 5. No surface may be reintroduced anywhere between the section and the
  //    tiles — the grid branch must stay free of panel utilities.
  const gridBranch = cards.slice(cards.indexOf('{cardsSubTab === "checklist" ? (\n                      <div className="min-w-0">'));
  assert.ok(!gridBranch.includes("set-glass-surface"), "no glass panel may wrap the card grid");
  assert.ok(!gridBranch.includes("backdrop-blur"), "no backdrop blur may sit between the artwork and the tiles");
});

test("one fixed ambient artwork layer persists with a reduced-motion-safe low-cost glow", () => {
  assert.equal((source.match(/data-set-ambient-artwork/g) || []).length, 1);
  assert.ok(source.includes("selectedTarget?.hero_image_url || selectedTarget?.logo_image_url"));
  assert.match(source, /data-set-ambient-artwork[\s\S]+pointer-events-none fixed inset-0 -z-10/);
  assert.ok(source.includes("set-page-atmosphere pointer-events-none fixed"));
  assert.ok(source.includes("object-contain object-center"));
  assert.ok(source.includes("set-page-atmosphere-artwork"));
  assert.ok(source.includes("set-page-atmosphere-bloom"));
  // Every knob is a --set-artwork-* token in globals.css so the treatment is
  // retuned in one place. The markup must not hardcode an opacity or filter,
  // and no tab may introduce its own override.
  assert.ok(
    !/set-page-atmosphere-(artwork|bloom)[^"]*(opacity-|brightness\(|saturate\(|grayscale\()/.test(source),
    "the artwork layers must not hardcode opacity or filter values in markup"
  );
  assert.ok(!source.includes("data-set-ambient-artwork animate-"));
  assert.match(globals, /\.set-page-atmosphere-artwork \{[\s\S]+opacity: var\(--set-artwork-opacity\);[\s\S]+transform: translateY\(var\(--set-artwork-y-offset\)\);/);
  assert.match(globals, /\.set-page-atmosphere-bloom \{[\s\S]+opacity: var\(--set-artwork-bloom-opacity\);/);
  assert.match(globals, /@media \(min-width: 1024px\)[\s\S]+\.set-page-atmosphere \{[\s\S]+--set-artwork-y-offset: 28px;/);
  // Ambient, not foreground. brightness() on the crisp layer stays at or below
  // 1 so white-heavy artwork (151's numerals) cannot clip to pure white and
  // read as bright blocks behind the charts, and the bloom — the layer that
  // dominates perceived brightness — stays well under the crisp layer's reach.
  const artworkBrightness = Number(globals.match(/--set-artwork-brightness: ([\d.]+);/)[1]);
  assert.ok(artworkBrightness <= 1, `crisp artwork brightness must not exceed 1, got ${artworkBrightness}`);
  const artworkOpacityLg = Number(globals.match(/--set-artwork-opacity-lg: ([\d.]+);/)[1]);
  assert.ok(artworkOpacityLg > 0 && artworkOpacityLg <= 0.16, `artwork must stay ambient but visible, got ${artworkOpacityLg}`);
  const bloomOpacityLg = Number(globals.match(/--set-artwork-bloom-opacity-lg: ([\d.]+);/)[1]);
  assert.ok(bloomOpacityLg > 0 && bloomOpacityLg <= 0.18, `bloom must stay a glow, not a second image, got ${bloomOpacityLg}`);
  assert.match(globals, /\.set-page-atmosphere::after[\s\S]+animation: set-page-atmosphere-breathe 14s ease-in-out infinite;/);
  assert.match(globals, /@keyframes set-page-atmosphere-breathe[\s\S]+opacity: 0\.34;[\s\S]+opacity: 0\.52;/);
  assert.match(globals, /@media \(prefers-reduced-motion: reduce\)[\s\S]+\.set-page-atmosphere::after[\s\S]+animation: none;/);
  assert.ok(!globals.includes("filter: brightness"));
  assert.ok(!source.includes("Paldean Fates"));
});

test("opening economics live in Overview Opening Profit vs Cost", () => {
  const start = source.indexOf('id="set-detail-overview-performance"');
  const end = source.indexOf('id="set-detail-top-market-cards"', start);
  const overview = source.slice(start, end);
  assert.ok(overview.includes('title="Opening Profit vs Cost"'));
  assert.ok(overview.includes("data-overview-opening-economics"));
  assert.ok(overview.includes("headerDecisionMetrics.map"));
  assert.ok(overview.includes("headerExpectedLossText"));
  assert.ok(
    overview.indexOf("<PackValueHistoryChart") < overview.indexOf("data-overview-opening-economics"),
    "the opening profit chart must render before its supporting metrics"
  );
  // The desktop three-column subgrid moved from `sm:` to `desk:`. `max-*`
  // variants are emitted before `sm:` in the stylesheet, so an sm-scoped
  // desktop grid would have won back the 640-1199px band and undone the mobile
  // compaction. Desktop at 1200px+ renders the identical subgrid.
  assert.ok(overview.includes("desk:grid-rows-[auto_auto_auto]"));
  assert.ok(overview.includes("desk:row-span-3 desk:grid-rows-subgrid"));
  assert.ok(overview.includes("md:whitespace-nowrap"));
  assert.ok(overview.includes("text-sm font-semibold tabular-nums"));
  assert.ok(overview.includes('<span aria-hidden="true" className="hidden desk:inline">&nbsp;</span>'));

  // Below desktop the same metrics render as compact label/value rows.
  assert.ok(overview.includes("data-opening-metric-row"), "each metric is an identifiable compact row");
  assert.ok(overview.includes("grid-cols-[minmax(0,1fr)_auto]"), "label and value share one line below desktop");
});

test("Insights verdict owns the score mode and complete static Opening Outlook", () => {
  const start = source.indexOf("function RipScoreBreakdownModule");
  const end = source.indexOf("function StatTile", start);
  const verdict = source.slice(start, end);
  assert.ok(verdict.includes("<RipScoreModeToggle"));
  assert.ok(verdict.includes("data-insights-opening-outlook"));
  assert.ok(verdict.includes("openingOutlook ||"));
  assert.ok(verdict.includes("It does not evaluate sealed-product appreciation"));
  assert.ok(!verdict.includes("<details"));
  assert.ok(!verdict.includes("Read full outlook"));
});

test("canonical hero selectors and premium chart treatment remain unchanged", () => {
  const metricsStart = source.indexOf("const headerDecisionMetrics = [");
  const metricsEnd = source.indexOf("const primaryDecisionMetricOrder", metricsStart);
  const metrics = source.slice(metricsStart, metricsEnd);
  assert.ok(metrics.includes("currentPackCost"));
  assert.ok(metrics.includes("averagePackValue"));
  assert.ok(metrics.includes("chanceToBeatPackCost"));
  assert.ok(!metrics.includes("averageHitValue"));
  assert.ok(!metrics.includes("chanceAtBigPull"));

  const compactStart = source.indexOf("function CompactSparkline");
  const compactEnd = source.indexOf("function normalizeSetValueHistoryPoints", compactStart);
  const compact = source.slice(compactStart, compactEnd);
  assert.ok(compact.includes('stopOpacity="0.12"'));
  assert.ok(compact.includes('strokeWidth="1.9"'));
  assert.ok(compact.includes("data-compact-sparkline-marker"));
  assert.ok(compact.includes("h-3 w-3"));
  assert.ok(compact.includes("h-1.5 w-1.5"));
});

test("overview charts and opening metric movement use restrained premium treatment", () => {
  const setValueChart = source.slice(
    source.indexOf("function SetValueLineChart"),
    source.indexOf("function SetValueTrendCard")
  );
  assert.ok(setValueChart.includes("<Area"));
  assert.ok(setValueChart.includes("baseValue={yMin}"));
  assert.ok(setValueChart.includes('stopOpacity="0.13"'));
  assert.ok(setValueChart.includes('stdDeviation="1.8"'));
  assert.ok(setValueChart.includes("strokeOpacity={0.16}"));

  const overviewStart = source.indexOf('title="Opening Profit vs Cost"');
  const overviewEnd = source.indexOf('id="set-detail-top-market-cards"', overviewStart);
  const overview = source.slice(overviewStart, overviewEnd);
  assert.ok(overview.includes("<OpeningMetricTrendIndicator"));
  assert.ok(overview.includes("neutral={metric.label === RIP_COPY.simpleMetrics.currentPackCost}"));
});
