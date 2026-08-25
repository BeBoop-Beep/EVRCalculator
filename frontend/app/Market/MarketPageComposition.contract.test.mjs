// The Pokémon Market page composition.
//
// Locked information hierarchy, in this order and no other:
//
//   header + tracked-data metadata
//   -> 7D Market Movers            (the EXISTING component, moved, unchanged)
//   -> Market Overview + Pokémon Market Performance   (ONE surface)
//   -> Set Market + Selected Set Analysis             (ONE surface)
//
// The two unification rules are the point of the redesign and are asserted
// structurally: neither pair may go back to being two independent cards.

import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

const here = path.dirname(new URL(import.meta.url).pathname.slice(1));
const read = (relative) => fs.readFileSync(path.resolve(here, relative), "utf8").replace(/\r\n/g, "\n");

const page = read("page.js");
const movers = read("../../components/explore/ExploreMarketMovers.jsx");
const ticker = read("../../components/explore/SevenDayMarketMoversTicker.jsx");
const analysis = read("../../components/explore/PokemonMarketAnalysis.jsx");
const overview = read("../../components/explore/PokemonMarketOverview.jsx");
const performance = read("../../components/explore/PokemonMarketPerformance.jsx");
const setMarket = read("../../components/explore/SetMarketExplorer.jsx");
const css = read("../../components/explore/explore.module.css");

// A source view with comments removed. Several assertions below are of the
// form "this file must NEVER mention X"; a prose comment explaining WHY it
// does not is exactly the thing that would otherwise fail them.
const codeOf = (source) => source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
const overviewCode = codeOf(overview);
const performanceCode = codeOf(performance);
const setMarketCode = codeOf(setMarket);

test("the page header carries the locked copy", () => {
  assert.match(page, />Pokémon Market</);
  assert.match(page, /Track the value and performance of the Pokémon card market\./);
  assert.doesNotMatch(page, /What is happening with Pokémon prices\?/);
});

test("sections render in the locked order — Movers first, then the two unified surfaces", () => {
  const order = ["ExploreMarketMovers", "PokemonMarketAnalysis", "SetMarketExplorer"];
  const positions = order.map((name) => page.indexOf(`<${name}`));
  assert.ok(positions.every((position) => position > 0), `every section must render: ${JSON.stringify(positions)}`);
  assert.deepEqual([...positions].sort((a, b) => a - b), positions, "sections must appear in the locked order");
  // Movers sits directly beneath the header metadata, above every analysis.
  assert.ok(page.indexOf("data-market-coverage-summary") < positions[0]);
});

test("7D Market Movers is the existing component, only relocated", () => {
  assert.match(movers, /SevenDayMarketMoversTicker/);
  assert.match(movers, /entry=\{payload\?\.marketMovers\}/);
  assert.match(movers, /scope="explore" thumbnailSize="medium"/);
  assert.match(movers, /maxItems=\{30\}/);
  assert.match(movers, />7D Market Movers</);
  assert.match(page, /<ExploreMarketMovers payload=\{moversPayload\} \/>/);
  // The heading stands alone — no descriptive subtitle between it and the
  // ticker, and no paragraph was left behind in the wrapper.
  assert.doesNotMatch(movers, /Largest card-price moves across tracked sets/);
  assert.doesNotMatch(movers, /<p/);
  // Its own data contract, controls and imagery are untouched.
  assert.match(ticker, /selectMoversTickerItems\(entry, \{ maxItems \}\)/);
  assert.match(ticker, /MoversTickerViewport/);
  assert.match(ticker, /7D Movers/);
});

test("Market Overview and Market Performance are ONE surface, not two cards", () => {
  // The wrapper owns the single surface...
  assert.match(analysis, /styles\.surfaceQuiet/);
  assert.match(analysis, /styles\.marketAnalysis/);
  assert.match(analysis, /<PokemonMarketOverview\n\s+overview=\{overview\}/);
  assert.match(analysis, /<PokemonMarketPerformance\n\s+overview=\{overview\}/);
  // ...and neither pane may reintroduce one of its own.
  assert.doesNotMatch(overview, /styles\.surfaceQuiet/);
  assert.doesNotMatch(performance, /styles\.surfaceQuiet/);
  assert.match(overview, /data-market-overview-pane/);
  assert.match(performance, /data-market-performance-pane/);
  // One grid, one hairline between the panes — not two bordered boxes.
  assert.match(css, /\.marketAnalysis \{/);
  assert.match(css, /\.marketAnalysis > section \+ section \{\n {4}border-left: 1px solid var\(--ex-line\);/);
  // Explicit floors on BOTH tracks: this is what makes a collision between the
  // table and the chart impossible rather than merely unlikely.
  assert.match(css, /grid-template-columns: minmax\(20rem, 42fr\) minmax\(22rem, 58fr\);/);
});

test("ONE timeframe state drives the overview period column and the chart", () => {
  // The state lives in the parent; neither pane may keep its own.
  assert.match(analysis, /const \[requestedWindow, setRequestedWindow\] = useState\(null\)/);
  assert.match(analysis, /resolveDefaultMarketWindow\(overview, "7D"\)/);
  assert.match(analysis, /selectedWindow=\{selectedWindow\}/);
  assert.match(analysis, /onWindowChange=\{setRequestedWindow\}/);
  assert.doesNotMatch(overview, /useState/);
  assert.doesNotMatch(performance, /useState/);
  // Both panes read the SAME prop, so they cannot disagree.
  assert.match(overview, /getPricePerformanceChange\(family, selectedWindow\)/);
  assert.match(performance, /buildMarketPerformanceSeries\(overview, selectedWindow\)/);
});

test("Market Overview is five columns and keeps BOTH published dimensions", () => {
  // Tracked Market Value plus the market's OWN since-tracking index return.
  assert.match(overview, /MARKET_OVERVIEW_GROUPS\.trackedValue/);
  assert.match(overview, /const SINCE_TRACKING = "All"/);
  // The Since Tracking column MUST read the family-specific series. Reading the
  // shared-comparison `changes` here reported the common comparable start under
  // a "Since Tracking" label, which is the defect this guards against.
  assert.match(overview, /getFamilySinceTrackingChange\(family\)/);
  assert.doesNotMatch(overview, /getPricePerformanceChange\(family, SINCE_TRACKING\)/);
  assert.match(overview, /data-market-overview-metric="trackedValue"/);
  // Price Performance: the index plus ONE dynamic period column, read from
  // changes at the shared selection.
  assert.match(overview, /MARKET_OVERVIEW_GROUPS\.pricePerformance/);
  assert.match(overview, /data-market-overview-metric="index"/);
  assert.match(overview, /data-market-overview-period-heading=\{selectedWindow\}/);
  // The old all-windows-at-once table is gone.
  assert.doesNotMatch(overview, /MARKET_OVERVIEW_SUMMARY_WINDOWS/);
  // No row sparklines — the chart beside it already is the temporal view.
  assert.doesNotMatch(overview, /Sparkline/);
});

test("Market Overview rows are the chart's legend and are generated from data", () => {
  // Each row carries the series identity swatch the chart draws with...
  assert.match(overview, /<MarketSwatch color=\{family\.color\} \/>/);
  assert.match(performance, /backgroundColor: family\.color/);
  // ...and every row is produced by mapping the published families, so a
  // Graded or Sealed market appears by publishing it, not by a redesign.
  assert.match(overview, /families\.map\(\(family\) =>/);
  assert.doesNotMatch(overviewCode, /"raw"|"topChase"|Graded|Sealed/);
  assert.doesNotMatch(performanceCode, /"raw"|"topChase"|Graded|Sealed/);
});

test("Market Performance defaults to 7D and keeps every published timeframe", () => {
  assert.match(analysis, /resolveDefaultMarketWindow\(overview, "7D"\)/);
  assert.match(analysis, /buildMarketWindowOptions\(overview\)/);
  assert.match(performance, /<MarketOverviewWindowSelector/);
  assert.doesNotMatch(analysis, /resolveDefaultMarketWindow\(overview, "30D"\)/);
});

test("Set Market and the selected-set analysis are ONE surface, not two cards", () => {
  assert.equal((setMarket.match(/styles\.surfaceQuiet/g) || []).length, 2, "one surface, plus its empty/error state");
  assert.match(setMarket, /styles\.setMarketBody/);
  assert.match(setMarket, /data-set-market-list/);
  assert.match(setMarket, /data-set-market-detail/);
  // The panes are grid children of one body divided by a hairline.
  assert.match(css, /\.setMarketBody \{/);
  assert.match(css, /\.setMarketDetail \{\n {4}border-left: 1px solid var\(--ex-line\);/);
});

test("the set list scales to a large catalogue: bounded scroll, no per-row chart", () => {
  assert.match(css, /\.setListScroll \{[\s\S]*?overflow-y: auto;/);
  assert.match(css, /\.setListScroll \{[\s\S]*?max-height: var\(--ex-set-market-scroll/);
  assert.equal((setMarket.match(/<MarketSparkline/g) || []).length, 1);
  // Rows are real buttons, so the list is keyboard navigable by construction.
  assert.match(setMarket, /data-set-market-row=\{row\.setId\}/);
  assert.match(setMarket, /aria-current=\{isActive \? "true" : undefined\}/);
});

test("selecting a set updates the pane in place and lazily loads only its full detail history", () => {
  assert.match(setMarket, /onClick=\{\(event\) => activateSetRow\(event, row, isActive\)\}/);
  assert.match(setMarket, /resolveSetMarketRowAction/);
  assert.doesNotMatch(setMarket, /setTimeout|doubleClickTimer/i);
  assert.match(setMarket, /setSelectedSetId/);
  // Rankings and movements stay on the compact publication; only the one
  // selected detail history uses the existing value-history client.
  assert.doesNotMatch(setMarket, /fetch\(/);
  assert.match(setMarket, /target\?\.currentSetValue/);
  assert.match(setMarket, /target\?\.windows\?\.\[listWindowKey\]/);
  assert.match(setMarket, /getPokemonSetValueHistory\(setId/);
  assert.match(setMarket, /detailHistoryCache\.current/);
  assert.doesNotMatch(setMarket, /targets\.map\([^)]*getPokemonSetValueHistory/);
});

test("mobile Set Market uses document scroll with a contextual sticky toolbar", () => {
  assert.match(css, /@media \(max-width: 1199\.98px\) \{[\s\S]*?\.setListScroll \{[\s\S]*?height: auto;[\s\S]*?max-height: none;[\s\S]*?overflow-y: visible;/);
  assert.match(css, /\.setMarketMobileSticky \{[\s\S]*?position: sticky;[\s\S]*?top: var\(--app-header-offset, 64px\);[\s\S]*?z-index: 30;/);
  assert.match(setMarket, /data-set-market-toolbar/);
  assert.match(setMarket, /setListHeaderMobile/);
  assert.match(setMarket, /data-set-market-results-top/);
  assert.match(setMarket, /<ReturnToTopButton/);
  assert.match(setMarket, /new IntersectionObserver/);
  assert.match(setMarket, /prefers-reduced-motion: reduce/);
  assert.match(css, /@media \(min-width: 1200px\) \{[\s\S]*?\.setMarketBody/);
});

test("mobile Set Market is list-only with passive truthful row sparklines", () => {
  assert.match(setMarket, /<MiniMarketSparkline points=\{miniTrend\}/);
  assert.match(setMarket, /selectSetMarketMiniTrend\(row\.target, listWindowKey\)/);
  assert.match(setMarket, /if \(!isMasterDetail \|\| !browserIsDesktop\) return undefined/);
  assert.match(setMarket, /<div className="hidden desk:block">\{detailPane\}<\/div>/);
  assert.doesNotMatch(setMarket, /mobileView|detailWindowKey|data-set-market-back/);
  assert.doesNotMatch(setMarket, /targets\.map\([^)]*getPokemonSetValueHistory/);
});

test("selected-set history loading is a silent, fixed-height chart skeleton", () => {
  assert.match(setMarket, /data-set-market-detail-skeleton/);
  assert.match(setMarket, /aria-hidden="true"/);
  assert.match(setMarket, /h-44[\s\S]*desk:h-\[15rem\]/);
  assert.doesNotMatch(setMarket, /Loading daily Set Value history|fetching snapshots/i);
  assert.match(setMarket, /Set Value history is temporarily unavailable\./);
});

test("the shared Set Market timeframe defaults to 7D", () => {
  assert.match(setMarket, /const DEFAULT_WINDOW = "7D"/);
  assert.match(setMarket, /useState\(DEFAULT_WINDOW\)/);
  assert.equal((setMarket.match(/useState\(DEFAULT_WINDOW\)/g) || []).length, 1, "one list window also drives the desktop detail chart");
});

test("selected-set Top Movers reuses the existing per-set movers data and selector", () => {
  const topMovers = read("../../components/explore/SetMarketTopMovers.jsx");
  assert.match(topMovers, /getPokemonSetMarketMovers/);
  assert.match(topMovers, /selectMoversTickerItems/);
  assert.match(topMovers, /const WINDOW = "7D"/);
  assert.match(topMovers, /const LIMIT = 10/);
  // Lazy and per-selection: nothing is fetched until a set is selected.
  assert.match(topMovers, /if \(!setId\)/);
  assert.match(setMarket, /<SetMarketTopMovers key=\{selected\.setId\}/);
  // It does NOT reach into the approved page-level ticker component.
  assert.doesNotMatch(codeOf(topMovers), /SevenDayMarketMoversTicker/);
});

test("Top Movers is a fixed-height carousel that cannot move the page", () => {
  const topMovers = read("../../components/explore/SetMarketTopMovers.jsx");
  // Paging scrolls the TRACK, never the window or an ancestor.
  assert.match(topMovers, /track\.scrollBy\(\{ left: sign \*/);
  assert.doesNotMatch(topMovers, /window\.scroll|scrollIntoView/);
  assert.match(topMovers, /data-mover-carousel-step=/);
  assert.match(topMovers, /data-mover-carousel-track/);
  // Fixed card height and a single-row track: ten movers are as tall as three.
  assert.match(css, /\.moverCard \{[\s\S]*?height: 4\.5rem;/);
  // And the visible run divides the track EXACTLY, so no dead space is left
  // stranded at the right of the rail. A fixed basis cannot fill a fluid
  // container — that was the bug, and the comment naming it is why this
  // assertion reads the code rather than the whole file.
  assert.match(css, /flex: 0 0 calc\(\(100% - 2 \* var\(--mover-gap\)\) \/ 3\);/);
  const cssCode = css.replace(/\/\*[\s\S]*?\*\//g, "");
  assert.doesNotMatch(cssCode, /flex: 0 0 13rem/, "no fixed card width may return");
  // The floor that keeps a long card name from overriding that basis.
  assert.match(css, /\.moverCard \{[\s\S]*?min-width: 0;/);
  // The rail sizes off its own container, not the viewport — the detail pane
  // is a constant width at every desktop size, so a media query would be
  // measuring the wrong box.
  assert.match(css, /container-type: inline-size;/);
  assert.match(css, /@container mover-rail \(min-width: 47rem\)/);
  assert.match(css, /\.moverTrack \{[\s\S]*?overflow-x: auto;/);
  assert.match(css, /\.moverTrack \{[\s\S]*?overflow-y: hidden;/);
  // The loading placeholder reserves the same height, so arrival shifts nothing.
  assert.match(topMovers, /h-\[4\.5rem\] animate-pulse/);
});

test("Set Market controls use the shared dark form language, never a bright field", () => {
  assert.match(setMarket, /styles\.setMarketControl/);
  assert.equal((setMarket.match(/styles\.setMarketControl/g) || []).length, 1, "search remains the shared form control");
  assert.equal((setMarket.match(/<DarkSelect/g) || []).length, 2, "era and sort use the accessible dark popup control");
  assert.match(css, /\.setMarketControl \{[\s\S]*?background-color: var\(--surface-page\);/);
  assert.match(setMarket, /ariaLabel="Filter by era"/);
  assert.match(setMarket, /ariaLabel="Sort sets"/);
  const setMarketFocus = css.slice(css.indexOf(".setMarketControl:focus {"), css.indexOf("}", css.indexOf(".setMarketControl:focus {")) + 1);
  assert.match(setMarketFocus, /border-color: rgb\(45, 212, 191\);/);
  assert.match(setMarketFocus, /box-shadow: 0 0 0 2px rgba\(var\(--ex-teal\), 0\.35\);/);
  assert.doesNotMatch(setMarketFocus, /var\(--accent\)/);
});

test("multi-set comparison is NOT implemented", () => {
  // Explicitly out of scope: no multi-select, no compare affordance, no
  // second series on the selected-set chart, no upsell.
  // Word-bounded: localeCompare is a sort primitive, not a compare feature.
  assert.doesNotMatch(setMarketCode, /compare|comparison|compareSet|onCompare/i);
  assert.doesNotMatch(setMarketCode, /type="checkbox"/);
  assert.doesNotMatch(setMarketCode, /selectedSetIds|premium|upgrade/i);
  assert.equal((setMarket.match(/<MarketSparkline/g) || []).length, 1, "one set, one chart");
});

test("Market Overview is read from the snapshot, never computed in the frontend", () => {
  assert.match(page, /resolveMarketOverview\(setValuePayload\)/);
  assert.match(page, /setValuePayload\?\.sets/);
  assert.match(page, /projectMarketPageOverview\(overview\)/);
  assert.match(page, /overview=\{marketPageOverview\}/);
  // No local arithmetic on market figures.
  assert.doesNotMatch(page, /basketValue\s*[-+*/]/);
  assert.doesNotMatch(page, /indexValue\s*[-+*/]/);
});

test("the page still serves exactly two global snapshots in parallel", () => {
  assert.match(page, /Promise\.allSettled/);
  assert.match(page, /getExploreSetValueMarket\(\)/);
  assert.match(page, /getExploreMarketMovers\(\)/);
  assert.equal((page.match(/await fetch\(/g) || []).length, 0);
  assert.equal((page.match(/getExploreSetValueMarket\(\)/g) || []).length, 1);
});

test("Movers and Set Market render regardless of Market Overview availability", () => {
  assert.match(page, /<ExploreMarketMovers payload=\{moversPayload\} \/>/);
  assert.match(page, /<SetMarketExplorer targets=\{targets\} loadError=\{loadError\} \/>/);
  const conditionalOverview = /\{overview \?[\s\S]*<SetMarketExplorer/.test(page);
  assert.equal(conditionalOverview, false, "Set Market must not be gated on the overview");
});

test("metadata describes the page without claiming forecasts or capitalization", () => {
  // Scoped to the metadata literal: the surrounding comment legitimately names
  // the vocabularies the page refuses to use.
  const metadata = page.slice(page.indexOf("buildRouteMetadata({"), page.indexOf("export default"));
  assert.match(metadata, /Pokémon Market Index, Trends & Set Values — inDex/);
  assert.match(metadata, /Track Pokémon Raw Card, Top Chase, and Sealed market performance, market movers, and current set values\./);
  assert.doesNotMatch(metadata, /market cap/i);
  assert.doesNotMatch(metadata, /forecast|prediction|investment advice|live trading/i);
});
