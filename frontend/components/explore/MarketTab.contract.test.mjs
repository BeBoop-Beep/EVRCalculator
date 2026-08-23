import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const pageSource = fs.readFileSync(path.join(here, "RipStatisticsPageClient.jsx"), "utf8");

const MARKET_START = '{setDetailTab === "market" ? (';
const marketSection = pageSource.slice(
  pageSource.indexOf(MARKET_START),
  pageSource.indexOf("RETIRED: the pre-RIP-page Overview composition")
);

test("Market is a real canonical set-detail tab", () => {
  assert.ok(pageSource.includes('new Set(["overview", "market", "cards", "pull-rates", "insights"])'));
  const aliases = pageSource.slice(
    pageSource.indexOf("const SET_DETAIL_TAB_ALIASES = {"),
    pageSource.indexOf("};", pageSource.indexOf("const SET_DETAIL_TAB_ALIASES = {"))
  );
  assert.ok(!aliases.includes("market"), "market must not be aliased to any other tab");
  assert.ok(marketSection.startsWith(MARKET_START), "Market must have its own render branch");
});

test("set tabs preserve desktop labels and define the compact mobile presentation", () => {
  const tabBar = pageSource.slice(pageSource.indexOf("data-set-detail-sticky-tabs"));
  const optionsStart = tabBar.indexOf("options={[");
  const optionsBlock = tabBar.slice(optionsStart, tabBar.indexOf("]}", optionsStart));
  const order = [...optionsBlock.matchAll(/value: "([^"]+)", label: "([^"]+)"/g)].map((match) => match.slice(1));
  assert.deepEqual(order, [["overview", "RIP"], ["market", "Market"], ["cards", "Cards & Products"], ["pull-rates", "Pull Rates"]]);
  assert.ok(optionsBlock.includes('label: "Cards & Products", mobileLabel: "Cards"'));
  assert.equal((optionsBlock.match(/hideIconOnMobile: true/g) || []).length, 4);
  assert.ok(pageSource.includes('option.hideIconOnMobile ? "max-desk:hidden" : ""'));
  assert.ok(pageSource.includes('<span className="max-desk:hidden">{option.label}</span>'));
  assert.ok(pageSource.includes('<span className="hidden max-desk:inline">{option.mobileLabel}</span>'));
});

test("Market renders exactly the three production market sections", () => {
  // The tab was redesigned from four stacked cards into three sections. Set
  // Value and Sealed Market are no longer standalone cards: they are the Cards
  // and Sealed lenses inside the Market Overview, which is why neither mounts
  // its own module any more. The invariant is unchanged — each section mounts
  // exactly once, in a fixed reading order.
  for (const moduleName of ["SevenDayMarketMoversTicker", "SetMarketOverviewSection", "TopChaseCardsPanel"]) {
    assert.equal(
      (marketSection.match(new RegExp(`<${moduleName}\\b`, "g")) || []).length,
      1,
      `${moduleName} is mounted exactly once on Market`
    );
  }
  // Reading order: 7D Movers -> Market Overview -> Top 10 Chase Cards.
  const positions = ["SevenDayMarketMoversTicker", "SetMarketOverviewSection", "TopChaseCardsPanel"].map((moduleName) =>
    marketSection.indexOf(`<${moduleName}`)
  );
  assert.deepEqual(positions, [...positions].sort((left, right) => left - right));

  // The retired standalone cards must not linger beside the lenses that
  // replaced them, which would chart the same series twice on one tab.
  for (const retired of ["SetValueTrendCard", "TopChaseCardsModule", "SealedMarketTrendCard"]) {
    assert.equal((marketSection.match(new RegExp(`<${retired}\\b`, "g")) || []).length, 0, `${retired} was folded in`);
  }
});

test("Market carries no RIP evidence, no forecasts, and no Product RIP", () => {
  for (const forbidden of [
    "RipScoreBreakdownModule",
    "RipDistributionChart",
    "SimulationMetricsContent",
    "CollectorAppealBreakdown",
    "TopEVDriversContent",
    "OverviewRipSummary",
    "RipDecisionPage",
    "Product RIP",
    "forecast",
    "Forecast",
    "portfolio",
    "Portfolio",
  ]) {
    assert.ok(!marketSection.includes(forbidden), `${forbidden} must not appear on Market`);
  }
});

test("market-owned data loads for Market, not for RIP or Analysis", () => {
  assert.ok(
    pageSource.includes('const shouldRenderMarketOverviewData = setDetailTab === "market"'),
    "the slim /overview (Set Value) fetch is Market-owned"
  );
  assert.ok(
    pageSource.includes('const isMarketMoversConsumer = setDetailTab === "market"'),
    "the slim /market/movers fetch is Market-owned"
  );
  assert.ok(
    pageSource.includes('const shouldRenderMarketData = setDetailTab === "market"'),
    "market-dashboard hydration is Market-owned"
  );
  assert.ok(
    pageSource.includes('...(setDetailTab === "market" ? [setValueTrendScope || CANONICAL_SET_VALUE_SCOPE] : [])'),
    "non-canonical set-value scopes are only fetched where the scope selector renders"
  );
  // Sealed still owns its own prepared-snapshot request rather than widening
  // the page's shared fetches — it just does so from the Market Overview's
  // sealed lens now instead of from a standalone Sealed Market card.
  assert.ok(pageSource.includes("function useSealedSetMarket(setId)"), "sealed reads its own prepared snapshot");
  assert.ok(pageSource.includes("getPokemonSetSealedMarket(setId)"));
  assert.ok(marketSection.includes("<SetMarketOverviewSection"), "the sealed lens renders inside Market Overview");
});

test("Top Chase is shared by RIP and Market and never Market-only", () => {
  assert.ok(
    pageSource.includes('const shouldFetchTopChase = setDetailTab === "overview" || setDetailTab === "market"'),
    "a fresh RIP entry must not depend on having visited Market first"
  );
  // RIP takes a consumer preview from the same state; Market takes the table.
  assert.ok(pageSource.includes("chaseCards={topPricedCards}"), "RIP still receives chase cards");
  assert.ok(marketSection.includes("cards={topPricedCards}"), "Market still receives the Top 10 table cards");
  // Duplicate-request guards must remain in place for the shared fetch.
  assert.ok(pageSource.includes("lastTopChaseRequestKeyRef.current === topChaseRequestKey"));
});

test("pull rates stay available to RIP and to their own tab", () => {
  assert.ok(pageSource.includes('if (setDetailTab !== "pull-rates" && setDetailTab !== "overview")'));
});

test("market-owned deep links resolve to nodes Market actually renders", () => {
  const targets = pageSource.slice(
    pageSource.indexOf("const SET_DETAIL_SECTION_TARGETS = {"),
    pageSource.indexOf("\n};", pageSource.indexOf("const SET_DETAIL_SECTION_TARGETS = {"))
  );
  for (const [section, targetId] of [
    ["set-value-trend", "set-detail-market-set-value"],
    ["top-market-cards", "set-detail-market-top-chase"],
    ["market-movers", "set-detail-market-movers"],
    ["sealed-market", "set-detail-market-sealed"],
  ]) {
    assert.ok(
      targets.includes(`"${section}": { tab: "market", targetId: "${targetId}" }`),
      `${section} must point at Market's ${targetId}`
    );
    assert.ok(marketSection.includes(`id="${targetId}"`), `${targetId} must exist on Market`);
  }
  // The retired Overview OPvC chart is gone; its legacy link goes to the
  // surviving Analysis historical-trend sub-view instead of resurrecting it.
  assert.ok(
    targets.includes('"performance-vs-cost": { tab: "insights", targetId: ANALYSIS_SECTION_ID, graphMode: "historical-trend" }')
  );
});

test("the persistent set header is identity/context only", () => {
  const header = pageSource.slice(
    pageSource.indexOf("data-set-context-header"),
    pageSource.indexOf('{setDetailTab === "overview" ? (')
  );
  assert.ok(header.includes("data-set-context-release-date"));
  assert.ok(header.includes("data-set-context-total-cards"));
  assert.ok(header.includes("data-set-context-rip-rank"));
  assert.ok(header.includes("selectedName"));
  assert.ok(!header.includes("data-set-context-set-value"), "Set Value must not render in the universal title card");
  assert.ok(!header.includes("<MarketValueChange"), "the header no longer renders a market value figure");
  // Removed from the header only — the shell contract still carries it.
  assert.ok(pageSource.includes("setHeaderSummary.setValue.current"), "Set Value stays in the header data contract");
});
