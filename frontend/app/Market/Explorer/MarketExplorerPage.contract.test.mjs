// The Market Explorer route, and the drill-down that reaches it.
//
// Two things this pass must not break:
//   1. /Market stays the concise public market pulse — same sections, same
//      analytics, plus one restrained Explore affordance.
//   2. /Market/Explorer adds NO backend endpoint, NO new market math, and NO
//      second charting library. It is a product surface over published data.

import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

const here = path.dirname(new URL(import.meta.url).pathname.slice(1));
const read = (relative) => fs.readFileSync(path.resolve(here, relative), "utf8").replace(/\r\n/g, "\n");

const explorerPage = read("page.js");
const marketPage = read("../page.js");
const overview = read("../../../components/explore/PokemonMarketOverview.jsx");
const client = read("../../../components/explore/MarketExplorerClient.jsx");
const chart = read("../../../components/explore/MarketExplorerChart.jsx");
const filters = read("../../../components/explore/MarketExplorerFilters.jsx");
const details = read("../../../components/explore/MarketExplorerDetails.jsx");
const card = read("../../../components/explore/MarketExplorerSeriesCard.jsx");
const gate = read("../../../components/explore/MarketExplorerAccessGate.jsx");
const state = read("../../../lib/explore/marketExplorerState.mjs");
const series = read("../../../lib/explore/marketExplorerSeries.mjs");

// A source view with comments removed: several assertions are of the form
// "this file must NEVER mention X", and a comment explaining why it does not
// is exactly the thing that would otherwise fail them.
const codeOf = (source) => source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

// --- the route ------------------------------------------------------------

test("the route exists at /Market/Explorer with the locked header copy", () => {
  assert.ok(fs.existsSync(path.resolve(here, "page.js")));
  assert.match(explorerPage, />Market Explorer</);
  assert.match(explorerPage, /Compare performance across Pokémon market segments\./);
  assert.match(explorerPage, /Index Plus/);
  assert.match(explorerPage, /path: "\/Market\/Explorer"/);
});

test("the page reuses the existing Market layout conventions rather than a new identity", () => {
  for (const shared of ["styles.dashboard", "explore-glass-scope", "index-environment", "max-w-7xl", "PageArtworkAtmosphere"]) {
    assert.ok(explorerPage.includes(shared), shared);
  }
});

test("the page consumes the EXISTING global market payload — no new endpoint, no new math", () => {
  assert.match(explorerPage, /getExploreSetValueMarket/);
  assert.match(explorerPage, /resolveMarketOverview/);
  // Exactly one backend read; the same snapshot /Market already fetches.
  assert.equal((explorerPage.match(/getExploreSetValueMarket\(/g) || []).length, 1);
  assert.ok(!explorerPage.includes("fetch("), "the page must not open its own endpoint");
});

test("URL parsing lives in one central parser, not spread through components", () => {
  assert.match(explorerPage, /resolveInitialExplorerState\([\s\S]{0,120}sealedSegments, cardSegments/);
  for (const [name, source] of Object.entries({ client, chart, filters, details, card })) {
    assert.ok(!source.includes("searchParams"), `${name} must not read the URL itself`);
    assert.ok(!source.includes("useSearchParams"), `${name} must not read the URL itself`);
  }
  assert.match(state, /export function parseMarketExplorerQuery/);
  // Serialization lives beside parsing, so the two cannot drift apart.
  assert.match(state, /export function serializeMarketExplorerQuery/);
  assert.match(state, /segments/);
});

// --- no invented analytics ------------------------------------------------

test("no Market Explorer component derives a market number in the browser", () => {
  for (const [name, source] of Object.entries({ client, chart, filters, details, card, state })) {
    const code = codeOf(source);
    // The classic frontend re-derivation of a published percentage.
    assert.ok(!/\/\s*first\s*-\s*1/.test(code), `${name} must not re-derive a percentage`);
    assert.ok(!/basketValue\s*[/*+-]/.test(code), `${name} must not do arithmetic on a basket value`);
    assert.ok(!/indexValue\s*[/*+-]/.test(code), `${name} must not do arithmetic on an index value`);
    assert.ok(!/\.percent\s*[/*+-]\s*[^ )]/.test(code.replace(/Math\.abs\(change\.percent\)/g, "")), `${name} must not do arithmetic on a published percent`);
  }
});

test("the comparison chart reuses the existing primitive — no second chart library", () => {
  assert.match(chart, /import MarketPerformanceChart from "\.\/MarketPerformanceChart"/);
  // Parents and submarkets go through ONE generalized model built on the same
  // published comparison windows, not a second series builder.
  assert.match(chart, /buildExplorerChartModel/);
  assert.match(series, /export function buildExplorerChartModel/);
  for (const source of [client, chart, details, card, filters]) {
    assert.ok(!/from "recharts"/.test(source), "no second charting library");
    assert.ok(!/d3/.test(source), "no second charting library");
  }
});

test("no era index is invented in the browser", () => {
  const code = [client, chart, filters, details, card, state, series].map(codeOf).join("\n");
  for (const forbidden of ["eraIndex", "Scarlet & Violet", "Sword & Shield", "Sun & Moon"]) {
    assert.ok(!code.includes(forbidden), `${forbidden} is still out of scope`);
  }
});

test("card-rarity options come from the payload, never from a hardcoded list", () => {
  // The identity table may name a rarity (label and color have to live
  // somewhere), but the OPTIONS the user sees are resolved from the published
  // `cardSegments` collection, so an unpublished rarity cannot appear.
  assert.match(series, /export function resolveCardSegmentSeries/);
  assert.match(state, /export function resolveAvailableCardSegmentIds/);
  for (const forbidden of ["specialIllustrationRare", "Special Illustration Rare", "ultraRare", "Ultra Rare"]) {
    assert.ok(!filters.includes(forbidden), `the filter must not hardcode ${forbidden}`);
  }
});

test("card segments are grouped by the parent market they measure", () => {
  assert.match(state, /Raw Card Segments/);
  assert.match(state, /Chase Segments/);
  assert.match(filters, /data-market-explorer-filter-group=\{group\.parentMarket\}/);
  // And a card series id carries its parent universe, so a Raw SIR index and a
  // Chase SIR index can never be confused for one another.
  assert.match(series, /card:\$\{parentMarket\}:\$\{backendKey\}|`\$\{CARD_SEGMENT_PREFIX\}\$\{parentMarket\}:\$\{backendKey\}`/);
  assert.match(series, /export function parseCardSeriesId/);
});

test("Top Chase rarity segments are stated as unpublished rather than faked", () => {
  assert.match(series, /export function resolveTopChaseSegmentStatus/);
  assert.match(filters, /data-market-explorer-chase-segments-unavailable/);
  // No component invents Top Chase membership by re-ranking cards.
  const code = [client, chart, filters, details, card, state, series].map(codeOf).join("\n");
  assert.ok(!/\.sort\([^)]*price/i.test(code), "must not rank cards to reconstruct Top Chase");
  // Bare `.slice(0, 10)` is deliberately NOT matched: it is how an ISO date
  // is trimmed throughout this codebase, so it would be a false positive.
  assert.ok(!/topChaseMembership|rankCards|byPriceDesc/i.test(code), "must not reconstruct chase membership");
});

test("Sealed submarket options come from the payload, never from a hardcoded list", () => {
  // The identity table may name a segment (label and color have to live
  // somewhere), but the OPTIONS the user sees are resolved from the published
  // `sealedSegments` collection, so an unpublished segment cannot appear.
  assert.match(series, /export function resolveSealedSegmentSeries/);
  assert.match(series, /raw\.available !== true/);
  assert.match(state, /export function resolveAvailableSealedFamilyIds/);
  assert.ok(!filters.includes("boosterBox"), "the filter must not hardcode a segment key");
  assert.ok(!filters.includes("Booster Box"), "the filter must not hardcode a segment label");
});

test("era remains declared but explicitly unavailable", () => {
  assert.match(state, /id: "era",[\s\S]*?available: false/);
  // Sealed Product Family and Card Segment are LIVE, and dynamic rather than
  // hardcoded.
  assert.match(state, /id: "sealedFamily",[\s\S]*?available: true/);
  assert.match(state, /id: "sealedFamily",[\s\S]*?dynamic: true/);
  assert.match(state, /id: "cardSegment",[\s\S]*?available: true/);
  assert.match(state, /id: "cardSegment",[\s\S]*?dynamic: true/);
  assert.match(filters, /Coming soon/);
});

test("the Since Tracking column is locked to the family-specific series", () => {
  // The whole point of the Part A split: a column labelled "Since Tracking"
  // may only read `familyChanges`.
  assert.match(state, /dimension: "family"/);
  assert.match(details, /window\.dimension === "family"[\s\S]{0,80}getFamilyChange/);
  assert.ok(!/getPricePerformanceChange\(entry, "All"\)/.test(details));
});

test("the future filter state model is declared now so later phases extend it", () => {
  for (const field of ["assetUniverse", "eraIds", "segmentIds", "sealedFamilyIds", "timeframe"]) {
    assert.ok(state.includes(field), field);
  }
});

// --- component architecture ----------------------------------------------

test("the workspace is composed, not one giant page component", () => {
  for (const component of ["MarketExplorerChart", "MarketExplorerDetails", "MarketExplorerFilters", "MarketExplorerSeriesCard"]) {
    assert.ok(client.includes(component), component);
  }
  // No file in the surface is allowed to become the 1,000-line page.
  for (const [name, source] of Object.entries({ explorerPage, client, chart, filters, details, card })) {
    assert.ok(source.split("\n").length < 300, `${name} is too large (${source.split("\n").length} lines)`);
  }
});

// --- paywall --------------------------------------------------------------

test("the workspace is wrapped by a single named entitlement boundary", () => {
  assert.match(explorerPage, /<MarketExplorerAccessGate>/);
  assert.match(explorerPage, /<MarketExplorerClient/);
  assert.match(gate, /MARKET_EXPLORER_REQUIRED_PLAN/);
  // No invented entitlement state, and no second auth system.
  const gateCode = codeOf(gate);
  assert.ok(!/isPaid\s*=\s*(true|false)/.test(gateCode), "must not hardcode entitlement");
  assert.ok(!/localStorage|document\.cookie|signIn\(/.test(gateCode), "must not invent a second auth system");
});

// --- the existing Market homepage ----------------------------------------

test("/Market keeps its sections, order and analytics", () => {
  const order = ["ExploreMarketMovers", "PokemonMarketAnalysis", "SetMarketExplorer"];
  let cursor = -1;
  for (const component of order) {
    const index = marketPage.indexOf(`<${component}`);
    assert.ok(index > cursor, `${component} out of order`);
    cursor = index;
  }
  assert.match(marketPage, />Pokémon Market</);
  assert.match(marketPage, /Track the value and performance of the Pokémon card market\./);
  // Still exactly two backend requests — the drill-down added no data cost.
  assert.equal((marketPage.match(/getExploreSetValueMarket\(\)|getExploreMarketMovers\(\)/g) || []).length, 2);
});

test("the Market Overview exposes one header action plus one link per market row", () => {
  assert.match(overview, /data-market-explore-link="all"/);
  assert.match(overview, /Explore Market/);
  assert.match(overview, /export function marketExplorerHref/);
  assert.match(overview, /\/Market\/Explorer/);
  assert.match(overview, /\?market=\$\{encodeURIComponent\(marketKey\)\}/);
  // The affordance is a link on the existing row, not a new column.
  assert.equal((overview.match(/<th scope="col"/g) || []).length, 5);
});

test("the drill-down does not break the existing row-toggle interaction", () => {
  // The row still toggles series visibility, and now correctly ignores clicks
  // that land on the Explore link as well as on the toggle button.
  assert.match(overview, /onToggleMarket\?\.\(family\.key\)/);
  assert.match(overview, /closest\("button, a"\)/);
  assert.match(overview, /data-market-overview-toggle=\{family\.key\}/);
  assert.match(overview, /data-market-overview-mobile-toggle=\{family\.key\}/);
});

test("the mobile homepage gets the same compact affordance, not an analytical accordion", () => {
  const mobileBlock = overview.slice(overview.indexOf("data-market-overview-cards"));
  assert.match(mobileBlock, /data-market-explore-link=\{family\.key\}/);
  assert.ok(!mobileBlock.includes("MarketPerformanceChart"), "no chart added to the mobile homepage cards");
  assert.ok(!/details|summary/.test(mobileBlock), "no accordion added to the mobile homepage cards");
});
