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

test("Market renders exactly the four production market modules", () => {
  for (const moduleName of [
    "SetValueTrendCard",
    "TopChaseCardsModule",
    "SevenDayMarketMoversTicker",
    "SealedMarketTrendCard",
  ]) {
    assert.equal(
      (marketSection.match(new RegExp(`<${moduleName}\\b`, "g")) || []).length,
      1,
      `${moduleName} is mounted exactly once on Market`
    );
  }
  // Reading order: Set Value -> Top 10 Chase -> 7D Movers -> Sealed.
  const positions = ["SetValueTrendCard", "TopChaseCardsModule", "SevenDayMarketMoversTicker", "SealedMarketTrendCard"].map(
    (moduleName) => marketSection.indexOf(`<${moduleName}`)
  );
  assert.deepEqual(positions, [...positions].sort((left, right) => left - right));
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
  // Sealed Market owns its own prepared-snapshot request inside the component.
  assert.ok(marketSection.includes("<SealedMarketTrendCard setId={resolvedSetResourceId} />"));
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
