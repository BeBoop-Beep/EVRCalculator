const fs = require("fs");
const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");

const pagePath = path.resolve(__dirname, "RipStatisticsPageClient.jsx");
const componentPath = path.resolve(__dirname, "../ui/MarketValueChange.jsx");
const cardClientPath = path.resolve(__dirname, "../../lib/pokemon/pokemonSetCardsClient.js");
const marketClientPath = path.resolve(__dirname, "../../lib/pokemon/pokemonSetMarketClient.js");
const pricingContractPath = path.resolve(__dirname, "../../lib/pokemon/pricingSnapshotContract.mjs");
const moversRoutePath = path.resolve(__dirname, "../../app/api/tcgs/pokemon/sets/[setId]/market/movers/route.js");

const read = (file) => fs.readFileSync(file, "utf8").replace(/\r\n/g, "\n");
const section = (source, startToken, endToken) => {
  const start = source.indexOf(startToken);
  const end = source.indexOf(endToken, start);
  assert.ok(start >= 0, `missing ${startToken}`);
  assert.ok(end > start, `missing ${endToken}`);
  return source.slice(start, end);
};

test("shared component owns market formatting, direction icon, variants, and unavailable state", () => {
  const component = read(componentPath);
  assert.ok(component.includes("buildMarketValueChangeModel"));
  assert.ok(component.includes("<DeltaTrendIcon"));
  for (const variant of ["hero", "chart-summary", "table-row", "card-tile", "ticker", "tooltip"]) {
    assert.ok(component.includes(`${variant}:`) || component.includes(`\"${variant}\":`), `missing ${variant}`);
  }
  assert.ok(component.includes("model.hasReliableChange"));
  assert.ok(!component.includes("rounded-md border"));
  assert.ok(!component.includes(">\\u00b7"), "separator escape must not be emitted as a raw JSX text node");
  assert.ok(!component.includes(">\\u2014"), "neutral dash escape must not be emitted as a raw JSX text node");
  assert.ok(component.includes('<span aria-hidden="true">{"\\u2014"}</span>'));
  assert.ok(component.includes('<span aria-hidden="true">{"\\u00b7"}</span>'));
  assert.ok(component.includes("showWindowLabel = true"));
  assert.ok(component.includes('content = "both"'));
  assert.ok(component.includes('content === "value"'));
  assert.ok(component.includes('content === "change"'));
  assert.ok(component.includes("showWindowLabel && model.windowLabel"));
  assert.ok(component.includes('text-[var(--text-secondary)] opacity-80'));
  assert.ok(!component.includes("flex-wrap items-center gap-x-1 whitespace-nowrap"));
});

test("Set Value title card and full chart use the shared stack with matching amount, percent, and windows", () => {
  const source = read(pagePath);
  const titleCard = section(source, ">Set Value Trend</p>", "{/* 7D Movers ticker");
  assert.ok(titleCard.includes("<MarketValueChange"));
  assert.ok(titleCard.includes("changeAmount={setHeaderSummary.setValue.delta30dAmount}"));
  assert.ok(titleCard.includes("changePercent={setHeaderSummary.setValue.delta30dPercent}"));
  assert.ok(titleCard.includes('windowLabel="30D"'));
  assert.ok(titleCard.includes('variant="hero"'));
  assert.ok(!titleCard.includes("30D Delta"));
  assert.ok(!titleCard.includes("30D %"));

  const fullChart = section(source, "function SetValueTrendCard", "function OverviewMetricTile");
  assert.ok(fullChart.includes("changeAmount={deltaAmount}"));
  assert.ok(fullChart.includes("changePercent={deltaPercent}"));
  assert.ok(fullChart.includes("windowLabel={deltaWindowLabel}"));
  assert.ok(fullChart.includes('variant="chart-summary"'));
  assert.ok(!fullChart.includes("getDeltaBadgeStyle"));
});

test("Top Chase combines Price and Change into the shared selected-window stack", () => {
  const source = read(pagePath);
  const rows = section(source, "function TopMarketCardRow", "function getTopCardDeltaEntries");
  assert.ok(rows.includes("<MarketValueChange"));
  assert.ok(rows.includes("changeAmount={displayDeltaAmount}"));
  assert.ok(rows.includes("changePercent={displayDelta}"));
  assert.ok(rows.includes("windowLabel={getDeltaWindowLabel(selectedWindowKey)}"));
  assert.ok(rows.includes("Price / Change"));
  assert.ok(!rows.includes(">Change</span>"));
  assert.ok(!rows.includes("<DeltaTrendIcon"));
});

test("Top Chase prefers stored canonical short-window deltas and warns on chart mismatches", () => {
  const source = read(pagePath);
  const delta = section(source, "function getTopCardDeltaWindow", "function getTopCardsAvailableDeltaWindows");
  assert.ok(delta.includes('const storedMovement = ["1D", "7D", "30D"].includes(selectedWindowKey)'));
  assert.ok(delta.indexOf("if (storedMovement)") < delta.indexOf("if (selectedHistoryWindow)"));
  assert.ok(delta.includes('source: "stored-canonical"'));
  assert.ok(delta.includes('console.warn("[pokemon-market-delta]'));
  for (const token of ["startDate", "endDate", "currentPrice", "cardVariantId", "conditionId"]) {
    assert.ok(delta.includes(token), `missing ${token} mismatch diagnostic`);
  }
});

test("Cards tiles render one Price to Delta to Window market block", () => {
  const source = read(pagePath);
  const tile = section(source, "function ChecklistCardTile", "function getChecklistCardMarketPrice");
  assert.ok(tile.includes("<MarketValueChange"));
  assert.ok(tile.includes("changeAmount={marketDelta?.amount}"));
  assert.ok(tile.includes("changePercent={marketDelta?.percent}"));
  assert.ok(tile.includes("windowLabel={movementWindow}"));
  assert.ok(tile.includes('windowLabelPlacement="below"'));
  assert.ok(tile.includes("accessiblePeriodLabel={getMovementAccessiblePeriod(marketDelta)}"));
  assert.ok(tile.includes('alignment="right"'));
  assert.ok(tile.includes('className="min-w-[7.5rem] shrink-0 text-right"'));
  assert.ok(!tile.includes('content="value"'));
  assert.ok(!tile.includes('content="change"'));
  assert.ok(tile.includes('movementWindow === "7D" ? getCardMovement7d(card) : getCardMovement30d(card)'));
  assert.ok(tile.includes('const cardMetaKey = `${getChecklistCardKey(card)}:${marketPrice ?? ""}:${marketDelta?.amount ?? ""}:${marketDelta?.percent ?? ""}:${movementWindow}`'));
  assert.ok(tile.includes("setIsMetaRevealed(false)"));
  assert.ok(tile.includes("[cardMetaKey, hasPriceData]"));
  assert.ok(!tile.includes("getDeltaBadgeStyle"));
  assert.ok(!tile.includes('content="value"\n                  showWindowLabel={false}'), "the value-only price must not carry visual movement configuration");
  assert.ok(source.includes('movementWindow={effectiveCardSortMode === "7d-movers" ? "7D" : "30D"}'));
  assert.ok(source.includes("displayedChecklistCards.map((card)"), "all visible and appended rows must reuse ChecklistCardTile");
  assert.ok(source.includes("dedupeChecklistCards([...previous.cards, ...payload.cards])"));
});

test("Set Value cards reserve enough height for the shared price/change stack", () => {
  const source = read(pagePath);
  const fullChart = section(source, "function SetValueTrendCard", "function OverviewMetricTile");
  assert.ok(fullChart.includes("min-h-[29rem]"));
  assert.ok(source.includes("min-h-[9.5rem]"));
  assert.ok(!source.includes("min-h-[8.25rem]"));
  assert.ok(!fullChart.includes("min-h-[26rem]"));
});

test("7D ticker and shared Set Value/Top Chase tooltip use the same stack without legacy pills", () => {
  const source = read(pagePath);
  const ticker = section(source, "function MoversTickerItemChip", "function MarketMoversTicker");
  assert.ok(ticker.includes("<MarketValueChange"));
  assert.ok(ticker.includes('windowLabel="7D"'));
  assert.ok(ticker.includes("showWindowLabel={false}"));
  assert.ok(!ticker.includes("<DeltaTrendIcon"));
  assert.ok(!ticker.includes("rounded-md border"));

  const tooltip = section(source, "function SetValueCompactTooltipCard", "function SetValueTooltip");
  assert.ok(tooltip.includes("<MarketValueChange"));
  assert.ok(tooltip.includes('variant="tooltip"'));
  assert.ok(!tooltip.includes("windowLabel="), "point-to-point tooltip change must not be mislabeled as a full window");
});

test("Top Chase and ticker hide the suffix while Cards place it below", () => {
  const source = read(pagePath);
  const topChase = section(source, "function TopMarketCardRow", "function InlinePanelSkeleton");
  const ticker = section(source, "function MoversTickerItemChip", "function MarketMoversTicker");
  const tile = section(source, "function ChecklistCardTile", "function getChecklistCardMarketPrice");
  for (const compactContext of [topChase, ticker]) {
    assert.ok(compactContext.includes("showWindowLabel={false}"));
    assert.ok(compactContext.includes("windowLabel="));
  }
  assert.ok(tile.includes('windowLabelPlacement="below"'));
  assert.ok(!tile.includes("showWindowLabel={false}"));
  assert.ok(source.includes("since the first available observation"));
  assert.ok(source.includes("topCardDeltaWindow?.isSinceFirstAvailable"));
  assert.ok(source.includes('className="flex h-14 min-w-0 items-center gap-2'));
});

test("normalizers retain authoritative 7D and 30D amount/percent pairs", () => {
  const cards = read(cardClientPath);
  const market = read(marketClientPath);
  for (const token of ["change30dAmount", "change30dPercent", "change7dAmount", "change7dPercent"]) {
    assert.ok(cards.includes(token), `cards normalizer missing ${token}`);
  }
  assert.ok(market.includes("change7dAmount: changeAmount"));
  assert.ok(market.includes("change7dPercent: changePercent"));
});

test("Cards, Top Chase, and Market Movers share pricing-v4", () => {
  const cards = read(cardClientPath);
  const market = read(marketClientPath);
  const shared = read(pricingContractPath);
  assert.ok(cards.includes('from "./pricingSnapshotContract.mjs"'));
  assert.ok(market.includes('from "./pricingSnapshotContract.mjs"'));
  assert.ok(shared.includes('PRICING_SNAPSHOT_CONTRACT_VERSION = "pricing-v4"'));
  assert.ok(!cards.includes('= "pricing-v3"'));
  assert.ok(!market.includes('= "pricing-v2"'));
  const route = read(moversRoutePath);
  assert.ok(route.includes('get("snapshot_contract")'));
  assert.ok(route.includes('backendUrl.searchParams.set("snapshot_contract", snapshotContract)'));
});

test("ticker thumbnail fills the three-line text stack without cropping", () => {
  const source = read(pagePath);
  const ticker = section(source, "function MoversTickerItemChip", "function MarketMoversTicker");
  assert.ok(ticker.includes("h-10 w-7"));
  assert.ok(ticker.includes("object-contain"));
  assert.ok(!ticker.includes("h-8 w-6"));
  assert.ok(!ticker.includes("object-cover"));
});

test("legacy market-price delta presentation code is absent", () => {
  const source = read(pagePath);
  assert.ok(!source.includes("function getDeltaBadgeStyle"));
  assert.ok(!source.includes("30D Delta"));
  assert.ok(!source.includes("30D %"));
  assert.ok(!source.includes('text-right">Change</span>'));
});
