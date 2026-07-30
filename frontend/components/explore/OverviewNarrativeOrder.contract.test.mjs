import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs
  .readFileSync(path.resolve(here, "RipStatisticsPageClient.jsx"), "utf8")
  .replace(/\r\n/g, "\n");

const overview = source.slice(
  source.indexOf('<section id="set-detail-overview"'),
  source.indexOf('{setDetailTab === "cards" ? (')
);

test("the Overview tells the brief's story in order", () => {
  // Both Overview grids stack in source order below desktop, so DOM order *is*
  // the mobile reading order. This is a regression lock, not a change.
  const order = [
    "set-detail-movers-ticker",
    "set-detail-set-value-trend",
    "Opening Profit vs Cost",
    "set-detail-top-market-cards",
    "set-detail-set-intelligence",
  ];
  let cursor = -1;
  for (const marker of order) {
    const found = overview.indexOf(marker, cursor + 1);
    assert.ok(found > cursor, `${marker} must appear after the previous section`);
    cursor = found;
  }
});

test("the local tabs precede the set identity, which precedes the feed", () => {
  // Mobile reading order is tabs -> identity -> content. Scope to the rendered
  // tree: `[data-set-detail-sticky-tabs]` also appears in
  // getExploreStickyOffset's querySelector, far above the JSX.
  const tree = source.slice(source.indexOf("{canRenderPrimaryContent ? ("));
  const tabs = tree.indexOf("data-set-detail-sticky-tabs");
  const mobileHero = tree.indexOf("<PokemonSetMobileHero");
  const feed = tree.indexOf('<section id="set-detail-overview" data-mobile-feed');
  assert.ok(tabs >= 0, "the tabs must be rendered");
  assert.ok(mobileHero > tabs, "the tabs come before the set identity below 1200px");
  assert.ok(feed > mobileHero, "the feed comes after the identity");

  // Desktop restores hero-above-tabs through flex order, not a second tree.
  assert.ok(source.includes("desk:order-1"), "the desktop hero takes the first slot at desktop");
  assert.ok(source.includes("desk:order-2"), "the tabs take the second slot at desktop");
  // One set-level navigation tree only. (SectionViewTabs is also used for the
  // Cards and Insights sub-tabs, so this counts the set-level bar specifically.)
  assert.equal(
    (source.match(/data-set-detail-sticky-tabs/g) || []).length,
    2,
    "the set-level tab bar is rendered once (plus its querySelector lookup)"
  );
  const tabBar = tree.slice(tree.indexOf("data-set-detail-sticky-tabs"));
  const optionsStart = tabBar.indexOf("options={[");
  const optionsBlock = tabBar.slice(optionsStart, tabBar.indexOf("]}", optionsStart));
  for (const destination of ["overview", "cards", "pull-rates", "insights"]) {
    assert.ok(optionsBlock.includes(`value: "${destination}"`), `${destination} destination must survive`);
  }
});

test("the movers strip is full width and cannot be clipped by its container", () => {
  assert.ok(overview.includes('<div id="set-detail-movers-ticker" className="min-w-0'));
});

test("the movers ticker preserves all ten items and its view-all destination", () => {
  const ticker = source.slice(
    source.indexOf("function MarketMoversTicker("),
    source.indexOf("function normalizePullRateAssumptions(")
  );
  assert.ok(ticker.includes("items.map("), "every selected mover is rendered");
  assert.ok(ticker.includes("View all movers"), "the view-all affordance survives");
  assert.ok(!/\.slice\(0,\s*\d+\)/.test(ticker), "the ticker must not truncate the selection");
  assert.ok(source.includes("const MOVERS_TICKER_FETCH_LIMIT = 10;"), "the fetch limit stays at ten");
});

test("nothing in this phase touched the movers rotation or its reduced-motion fallback", () => {
  const ticker = source.slice(
    source.indexOf("function MarketMoversTicker("),
    source.indexOf("function normalizePullRateAssumptions(")
  );
  // The marquee lives in MoversTickerViewport and is driven by its own
  // ResizeObserver; the strip must keep delegating to it rather than becoming
  // a static first item.
  assert.ok(ticker.includes("MoversTickerViewport"), "the rotation viewport still owns movement");
  assert.ok(ticker.includes("renderSequence"), "the repeating sequence is still handed to the viewport");
  const viewport = fs
    .readFileSync(path.resolve(here, "MoversTickerViewport.jsx"), "utf8")
    .replace(/\r\n/g, "\n");
  assert.ok(viewport.includes("prefers-reduced-motion"), "reduced motion is still respected");
  assert.ok(viewport.includes("ResizeObserver"), "the viewport still re-measures on resize");
});

test("no responsive branch can drop a mover or a chase card", () => {
  // Parity: composition and presentation may change with width (axis widths,
  // chart margins), but *membership* may not. These patterns are the ways a
  // width reading could start deciding which rows exist.
  for (const forbidden of [
    /moversTickerItems\s*\.slice\(/,
    /isDesktopComposition\s*\?\s*[a-zA-Z_$][\w$]*\s*:\s*[a-zA-Z_$][\w$]*\s*\.slice\(/,
    /isDesktopHeroComposition\s*\?\s*topPricedCards/,
    /maxRows=\{\s*isDesktop/,
    /slice\(0,\s*isDesktop/,
  ]) {
    assert.ok(!forbidden.test(source), `${forbidden} would make membership depend on width`);
  }

  // The one row cap that exists is driven by the user's expand control, never
  // by a breakpoint.
  assert.ok(source.includes("maxRows={showAllChaseCards ? 10 : 5}"), "the cap follows the user's choice");
});
