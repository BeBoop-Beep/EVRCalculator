import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs
  .readFileSync(path.resolve(here, "RipStatisticsPageClient.jsx"), "utf8")
  .replace(/\r\n/g, "\n");

const row = source.slice(
  source.indexOf("function TopMarketCardRow("),
  source.indexOf("function InlinePanelSkeleton(")
);
const module_ = source.slice(
  source.indexOf("function TopChaseCardsModule("),
  source.indexOf("function hasMarketMoverRows(")
);

test("the mobile row is a compact ranked row, not a stacked card", () => {
  // Rank, small image, name+rarity and price+movement share one line; the
  // sparkline spans beneath it. Unchanged by the desktop restoration.
  assert.ok(row.includes("grid-cols-[1.5rem_2.5rem_minmax(0,1fr)_auto]"), "the compact mobile grid is in place");
  assert.ok(row.includes('data-row-price="compact"'), "the compact price stays on the row's single line");
  assert.ok(row.includes("desk:hidden"), "the compact price is mobile/tablet only");
});

test("the desktop row is the four-column table again: rank | card | trend | price", () => {
  // The mobile composition briefly rendered rank | card | PRICE | trend, because
  // the price had moved inside the link and the chart could only be placed after
  // it. The row now declares the historical four-column template directly.
  assert.ok(
    row.includes("desk:grid-cols-[3rem_minmax(0,1fr)_minmax(11rem,17rem)_minmax(8rem,10rem)]"),
    "the restored desktop column template"
  );
  assert.ok(!row.includes("desk:grid-cols-[minmax(0,1fr)_minmax(9rem,14.5rem)]"), "the two-column regression is gone");

  // Columns 1-2 are the link (rank, card); 3 is the trend; 4 is the price.
  assert.ok(row.includes("desk:col-span-2 desk:col-start-1 desk:row-start-1"), "the link owns columns one and two");
  assert.ok(row.includes("desk:grid-cols-[3rem_minmax(0,1fr)]"), "the link splits into rank and card only");
  assert.ok(row.includes("desk:col-start-3 desk:row-start-1"), "the trend is column three");
  assert.ok(row.includes("desk:col-start-4 desk:row-start-1"), "the price is column four");
  assert.ok(row.includes('data-row-price="table"'), "the desktop price cell is identifiable");

  // Order, not just placement: the sparkline must precede the price cell.
  assert.ok(
    row.indexOf("desk:col-start-3") < row.indexOf("desk:col-start-4"),
    "the trend renders before the price so reading order matches visual order"
  );
});

test("the desktop price column never holds the chart, and the trend column never holds the price", () => {
  const chartStart = row.indexOf("data-row-chart");
  const chartEnd = row.indexOf('data-row-price="table"');
  assert.ok(chartStart >= 0 && chartEnd > chartStart, "both regions must be locatable and ordered");
  const chartRegion = row.slice(chartStart, chartEnd);
  assert.ok(chartRegion.includes("<MarketSparkline"), "the sparkline lives in the trend region");
  assert.ok(!chartRegion.includes("MarketValueChange"), "no price or delta may render in the trend column");
  const priceRegion = row.slice(chartEnd);
  assert.ok(priceRegion.includes("priceCell"), "the price region renders the shared price cell");
  assert.ok(!priceRegion.includes("MarketSparkline"), "no sparkline may render in the price column");
});

test("the desktop sparkline dimensions are the restored ones", () => {
  // 56px tall, capped at 13.75rem, centred in its column — the pre-mobile values
  // recovered from f310ee8.
  assert.ok(row.includes('className="w-full desk:max-w-[16rem]"'), "standardized desktop plot box");
  assert.ok(row.includes('plotClassName="h-12 desk:h-16"'), "64px desktop plot height");
  assert.ok(row.includes("desk:items-center"), "the plot is centred in the trend column");
  assert.ok(row.includes("desk:max-w-[16rem]"), "the status text keeps the plot's width");
  assert.ok(row.includes("desk:px-3 desk:py-3"), "the restored desktop row padding");
  assert.ok(row.includes("h-[4.875rem] w-14"), "the restored desktop card image box");
});

test("the price cell is computed once and rendered per composition", () => {
  // Duplicating the wrapper is the same pattern the card image already uses;
  // duplicating the computation would be a data risk.
  assert.equal((row.match(/const priceCell = \(/g) || []).length, 1, "one price cell definition");
  assert.equal((row.match(/<MarketValueChange/g) || []).length, 1, "one MarketValueChange instance");
  assert.equal((row.match(/\{priceCell\}/g) || []).length, 2, "rendered in exactly the two compositions");
});

test("every field the brief lists survives in the row", () => {
  for (const token of ["#{index + 1}", "{name}", "{rarity", "MarketValueChange", "MarketSparkline"]) {
    assert.ok(row.includes(token), `${token} must remain in the row`);
  }
  // Price, dollar movement and percentage movement all still flow through the
  // shared MarketValueChange, unchanged.
  for (const prop of ["value={price}", "changeAmount={displayDeltaAmount}", "changePercent={displayDelta}"]) {
    assert.ok(row.includes(prop), `${prop} must remain`);
  }
});

test("the information region is the link and the sparkline is its sibling", () => {
  // Correction 3: an interactive, focusable, arrow-key-driven chart must never
  // be nested inside a navigation anchor.
  assert.ok(row.includes('const NavigationRegion = href ? "a" : "div";'), "the nav region type follows the href prop");
  assert.ok(row.includes("data-row-nav"), "the navigation region is identifiable");
  assert.ok(row.includes("data-row-chart"), "the chart region is identifiable");

  const navStart = row.indexOf("<NavigationRegion");
  const navEnd = row.indexOf("</NavigationRegion>");
  assert.ok(navStart >= 0 && navEnd > navStart, "the navigation region must be locatable");
  assert.ok(
    !row.slice(navStart, navEnd).includes("MarketSparkline"),
    "the sparkline must not be rendered inside the anchor"
  );
  assert.ok(row.indexOf("MarketSparkline") > navEnd, "the chart region is a sibling that follows the link");
  assert.ok(row.includes("min-h-11"), "the row keeps a usable touch height");
});

test("the row never repairs nested semantics with stopPropagation", () => {
  // Match a call, not the explanatory comment above the composition.
  assert.ok(
    !/\.stopPropagation\s*\(/.test(row),
    "sibling composition removes the need to cancel propagation, which would only mask invalid nesting"
  );
});

test("the row destination keeps the set and the timeframe context", () => {
  assert.ok(source.includes("const topChaseRowHref = updateSetDetailQueryParams("), "the href is built from the shared builder");
  const hrefBlock = source.slice(
    source.indexOf("const topChaseRowHref = updateSetDetailQueryParams("),
    source.indexOf("});", source.indexOf("const topChaseRowHref = updateSetDetailQueryParams("))
  );
  assert.ok(hrefBlock.includes('tab: "cards"'), "chase rows lead into the Cards experience for this set");
  assert.ok(hrefBlock.includes('cardSort: "current-price"'), "the sort key must be one the Cards tab recognises");
  assert.ok(source.includes("rowHref={topChaseRowHref}"), "the destination reaches the module");
  assert.ok(source.includes("href={rowHref}"), "the destination reaches each row");
});

test("rows 6-10 are never discarded", () => {
  // Five rows is a preview only because the existing expand control still
  // reveals the full fetched list in place. Parity spec section 6.
  assert.ok(source.includes("maxRows={10}"), "all ten fetched rows remain rendered");
  assert.ok(module_.includes("Show ${hiddenRowCount} more"), "the reveal control survives");
  assert.ok(module_.includes("Show fewer chase cards"), "the collapse control survives");
  assert.ok(module_.includes("totalRows > TOP_CHASE_MOBILE_PREVIEW_LIMIT"), "the control appears whenever there is more than the preview");
  assert.ok(!module_.includes("showAllChaseCards ? 10 : 6"), "the old six-row preview is gone");
});

test("the column labels move with the desktop grid", () => {
  const content = source.slice(
    source.indexOf("function TopMarketCardsContent("),
    source.indexOf("function getTopCardDeltaEntries(")
  );
  assert.ok(content.includes("text-[var(--text-secondary)] desk:grid"), "labels appear only where the desktop grid does");
  assert.ok(!content.includes("text-[var(--text-secondary)] lg:grid"), "labels must not sit over the compact tablet rows");
});

test("loading placeholders match the final compact row height", () => {
  assert.ok(source.includes("data-top-chase-skeleton"), "the chase skeleton is distinguishable");
  assert.ok(source.includes("max-desk:h-[4.25rem]"), "the placeholder matches the compact row box");
});
