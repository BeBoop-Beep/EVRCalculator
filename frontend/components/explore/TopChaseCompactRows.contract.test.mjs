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
  // sparkline spans beneath it.
  assert.ok(row.includes("grid-cols-[1.5rem_2.5rem_minmax(0,1fr)_auto]"), "the compact mobile grid is in place");
  // Desktop keeps its four reading columns: rank | card | trend | price. The
  // trend is now a sibling placed into the second column of the outer grid.
  assert.ok(row.includes("desk:grid-cols-[minmax(0,1fr)_minmax(9rem,14.5rem)]"), "the outer desktop grid reserves the trend column");
  assert.ok(row.includes("desk:grid-cols-[3rem_minmax(0,1fr)_minmax(8rem,10rem)]"), "the desktop link keeps rank, card and price");
  assert.ok(row.includes("desk:col-start-2 desk:row-start-1"), "the trend column sits beside the link at desktop");
});

test("every field the brief lists survives in the row", () => {
  for (const token of ["#{index + 1}", "{name}", "{rarity", "MarketValueChange", "CompactSparkline"]) {
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
    !row.slice(navStart, navEnd).includes("CompactSparkline"),
    "the sparkline must not be rendered inside the anchor"
  );
  assert.ok(row.indexOf("CompactSparkline") > navEnd, "the chart region is a sibling that follows the link");
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
  assert.ok(module_.includes("showAllChaseCards ? 10 : 5"), "the preview is five rows and the expansion is ten");
  assert.ok(module_.includes("View all chase cards"), "the reveal control survives");
  assert.ok(module_.includes("Show fewer chase cards"), "the collapse control survives");
  assert.ok(module_.includes("totalRows > 5"), "the control appears whenever there is more than the preview");
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
