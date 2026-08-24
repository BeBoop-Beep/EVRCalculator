import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (relative) => fs.readFileSync(path.join(here, relative), "utf8");

const page = read("../../../explore/RipStatisticsPageClient.jsx");
const shell = read("./SetMarketMobile.jsx");
const hero = read("./SetMarketMobileHero.jsx");
const movers = read("./SetMarketMobileMovers.jsx");
const setValue = read("./SetMarketMobileSetValue.jsx");
const topChase = read("./SetMarketMobileTopChase.jsx");
const model = read("./setMarketMobileModel.mjs");

// These files carry long explanatory comments that legitimately discuss prices
// and metrics the code does not render ("$1k", "market cap"). The assertions
// below are about CODE, so comments are removed before scanning.
const code = (source) =>
  source
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .split("\n")
    .map((line) => line.replace(/^\s*\/\/.*$/, " "))
    .join("\n");

const marketBranch = page.slice(
  page.indexOf('{setDetailTab === "market" ? ('),
  page.indexOf("RETIRED: the pre-RIP-page Overview composition")
);

test("the mobile composition renders the three Market sections in the required order, with no duplicate set-identity card", () => {
  const order = ["SetMarketMobileMovers", "SetMarketMobileSetValue", "SetMarketMobileTopChase"];
  const positions = order.map((name) => shell.indexOf(`<${name}`));
  assert.ok(positions.every((position) => position > 0), "every section is mounted");
  assert.deepEqual(positions, [...positions].sort((left, right) => left - right), "movers → market snapshot → top chase");
  // The primary mobile set header already renders once, above the tab
  // navigation. A second identity card inside Market repeated it; it was
  // removed so 7D Movers is the first Market-content module.
  assert.equal(shell.includes("SetMarketMobileHero"), false, "no duplicate set-identity card is mounted inside Market");
});

test("mobile no longer mounts a standalone Sealed Market module", () => {
  // A dedicated lower-page Sealed Market section (its own product chips, its
  // own chart, its own metrics) used to sit below Top Chase. It is gone by
  // design — Market Snapshot's Sealed lens already answers what it did, and
  // the file backing it was deleted rather than merely unmounted, so there is
  // no orphaned component left to accidentally re-wire back in.
  assert.equal(shell.includes("SetMarketMobileSealed"), false, "the standalone Sealed Market component is not imported");
  assert.equal(fs.existsSync(path.join(here, "SetMarketMobileSealed.jsx")), false, "the file itself was removed, not just unmounted");
  assert.equal((shell.match(/<Section(ErrorBoundary)?\b/g) || []).length > 0, true);
});

test("each mobile section is independently boundaried so one failure cannot take the tab down", () => {
  assert.equal((shell.match(/<SectionErrorBoundary\b/g) || []).length, 3);
});

test("the removed section's deep-link id is preserved as an inert anchor, not a blank wrapper", () => {
  // set-detail-market-sealed used to be its own SectionErrorBoundary/card. It
  // is now a zero-height anchor inside Market Snapshot — the section that
  // actually answers what that old link promised — so an existing
  // ?section=sealed-market link still scrolls somewhere meaningful instead of
  // landing on nothing, while nothing renders for the removed module itself.
  const setValueBoundaryStart = shell.indexOf('sectionName="market-mobile-set-value"');
  const nextBoundaryStart = shell.indexOf("<SectionErrorBoundary", shell.indexOf(">", setValueBoundaryStart));
  const setValueBlock = shell.slice(setValueBoundaryStart, nextBoundaryStart === -1 ? shell.length : nextBoundaryStart);
  assert.ok(setValueBlock.includes("id={sectionIds.sealed}"), "the anchor lives inside the Market Snapshot boundary");
  assert.ok(/<span[^>]*id=\{sectionIds\.sealed\}[^>]*aria-hidden="true"/.test(setValueBlock), "it is an inert, invisible anchor");
});

test("exactly one Market composition mounts, chosen by the same 1200px reading the page already makes", () => {
  assert.ok(marketBranch.includes("isDesktopHeroComposition ? null : ("), "mobile renders only below 1200px");
  assert.ok(
    marketBranch.includes('{setDetailTab === "market" && isDesktopHeroComposition ? ('),
    "the desktop grid renders only at 1200px and above"
  );
  assert.equal((marketBranch.match(/<SetMarketMobile\b/g) || []).length, 1, "the mobile composition is mounted once");
  assert.ok(
    page.includes('const isDesktopHeroComposition = useMediaQuery("(min-width: 1200px)", true)'),
    "no second width source is introduced"
  );
});

test("desktop Market mounts its own production modules exactly once, unaffected by the mobile Sealed removal", () => {
  // The desktop composition is untouched by this pass: the shared 7D Movers
  // strip, one Market Overview (Cards/Sealed/Graded lenses), and Top 10 Chase
  // Cards. No module is mounted twice, and the two compositions never mount
  // each other's.
  for (const moduleName of ["SevenDayMarketMoversTicker", "SetMarketOverviewSection", "TopChaseCardsPanel"]) {
    assert.equal(
      (marketBranch.match(new RegExp(`<${moduleName}\\b`, "g")) || []).length,
      1,
      `${moduleName} is mounted exactly once, by the desktop branch only`
    );
    assert.equal(shell.includes(moduleName), false, `${moduleName} is not re-mounted by the mobile composition`);
  }

  for (const retired of ["SetValueTrendCard", "TopChaseCardsModule", "SealedMarketTrendCard"]) {
    assert.equal(
      (marketBranch.match(new RegExp(`<${retired}\\b`, "g")) || []).length,
      0,
      `${retired} was folded into the redesigned composition and must not still mount`
    );
  }

  // Desktop keeps its own Sealed lens (inside SetMarketOverviewSection) intact
  // — this pass removes only the standalone MOBILE module. useSealedSetMarket
  // is defined once, above the JSX return, and used by both the desktop lens
  // and the mobile Market Snapshot lens.
  assert.ok(page.includes("function useSealedSetMarket(setId)"), "the shared sealed data hook is untouched");
});

test("mobile reuses the desktop deep-link anchors so ?section= resolves at both widths", () => {
  for (const targetId of [
    "set-detail-market",
    "set-detail-market-set-value",
    "set-detail-market-top-chase",
    "set-detail-market-movers",
    "set-detail-market-sealed",
  ]) {
    assert.ok(marketBranch.includes(`"${targetId}"`) || marketBranch.includes(`id="${targetId}"`), `${targetId} exists on Market`);
  }
});

test("no mockup content is hardcoded anywhere in the mobile composition", () => {
  const sources = { shell, hero, movers, setValue, topChase, model };
  for (const [name, raw] of Object.entries(sources)) {
    const source = code(raw);
    assert.equal(/Pitch Black|Paldea Evolved|Prismatic Evolutions|Ascended Heroes/.test(source), false, `${name} names no specific set`);
    // No literal money, percentage or count is ever rendered as data. Currency
    // appears only through Intl formatters fed by the payload.
    assert.equal(/["'>]\s*\$\d/.test(source), false, `${name} renders no literal price`);
    assert.equal(/>\s*[+-]?\d+(\.\d+)?%/.test(source), false, `${name} renders no literal percentage`);
  }
});

test("no unavailable metric is invented", () => {
  for (const [name, raw] of Object.entries({ hero, movers, setValue, topChase, model })) {
    const source = code(raw);
    for (const forbidden of ["Market Cap", "market_cap", "marketCap", "Population", "populationCount", "Raw Copies", "Print Run", "printRun"]) {
      assert.equal(source.includes(forbidden), false, `${name} must not claim ${forbidden}`);
    }
  }
});

test("Market Snapshot and Top Chase own their own timeframe controls and no page-level master toggle is added", () => {
  assert.ok(setValue.includes("<MarketWindowSelector"), "Market Snapshot carries its own window selector");
  assert.ok(topChase.includes("<MarketWindowSelector"), "Top Chase carries its own window selector");
  // The shell is composition only — it must not hoist a shared timeframe.
  assert.equal(/WindowSelector|TimeRangeSelector|windowKey/.test(shell), false, "the tab has no master timeframe");
});

test("Market Snapshot reads the same segment model the desktop Market Overview reads", () => {
  // Market Snapshot switched from a Cards/Top10 SCOPE control to the same
  // Cards/Sealed/Graded LENS model desktop's SetMarketOverviewSection uses —
  // `selectSegmentTrend` and friends from setMarketOverviewModel.mjs — so a 7D
  // move, an unavailable lens, and a tracked-item count all mean the same
  // thing in both compositions.
  assert.ok(setValue.includes("selectPreparedSegmentTrend"));
  assert.ok(setValue.includes("unavailableSegmentTrend"));
  assert.ok(setValue.includes("setMarketOverviewModel.mjs"));
  // No local arithmetic on a value, delta or window.
  assert.equal(/currentValue\s*[-+*/]/.test(setValue), false, "Market Snapshot computes nothing of its own");
});

test("Market Snapshot offers exactly Cards, Sealed, Graded — not ranking scopes", () => {
  // The options are derived from buildMarketSegmentRows (the same desktop
  // selector), not a static array, so an unavailable lens can be disabled
  // rather than clickable-then-reverting.
  assert.ok(setValue.includes("buildMarketSegmentRows(trendsByKey)"));
  assert.ok(setValue.includes("disabled: !row.selectable"));
  assert.equal(/\btop10\b/i.test(code(setValue)), false, "Top 10 is a chase-card rank, not a market lens");
  assert.equal(setValue.includes("SET_VALUE_TREND_VISIBLE_SCOPE_OPTIONS"), false, "the old scope selector is retired here");
});

test("Market Snapshot defaults to Cards and 7D", () => {
  assert.match(setValue, /useState\("cards"\)/, "the segment control opens on Cards");
  assert.match(setValue, /useState\("7D"\)/, "the timeframe control opens on 7D");
});

test("an unavailable lens in Market Snapshot never fabricates a value", () => {
  const body = code(setValue);
  assert.ok(body.includes("SEGMENT_UNAVAILABLE_TEXT"));
  assert.ok(!/\|\|\s*0\b/.test(body), "no numeric zero fallback for a missing market value");
  assert.ok(!/\$0\b/.test(body), "no literal $0 is ever rendered");
});

test("Market Breadth and Chase Concentration are Cards-only micro-stats on mobile", () => {
  assert.ok(setValue.includes('segmentKey === "cards"'), "breadth/concentration are gated to the Cards lens");
  assert.ok(setValue.includes("selectPreparedMarketBreadth"));
  assert.ok(setValue.includes("selectChaseConcentration"));
});

test("Market Snapshot supporting details render as a compact micro-stat grid, not cards", () => {
  assert.ok(setValue.includes("data-market-mobile-micro-stats"));
  assert.ok(setValue.includes("grid-cols-2"), "a two-column micro-stat grid, not a stacked card list");
  assert.ok(setValue.includes("buildSupportingDetails"), "the six fields reuse the shared desktop selector");
});

test("Market Snapshot fetches sealed data itself, the same way the removed standalone module did", () => {
  // The dedicated Sealed Market fetch pattern is preserved — just relocated
  // inside Market Snapshot's own Sealed lens rather than a separate module.
  assert.ok(setValue.includes("getPokemonSetSealedMarket"), "the same slim sealed request backs the Sealed lens");
  assert.ok(setValue.includes("useSealedSetMarket"));
});

test("7D Movers is fixed to 7D and offers no window control", () => {
  assert.ok(movers.includes('title="7D Market Movers"'));
  assert.equal(/WindowSelector|TimeRangeSelector/.test(movers), false);
  assert.ok(movers.includes("selectMoversTickerItems") || model.includes("selectMoversTickerItems"));
});

test("the movers rail is a deliberate snap carousel, not accidental overflow", () => {
  assert.ok(movers.includes("snap-x") && movers.includes("snap-mandatory") && movers.includes("snap-start"));
  assert.ok(movers.includes("overflow-x-auto"));
});

test("Top Chase is a featured card plus a ranked list, with no per-row sparkline", () => {
  assert.ok(topChase.includes("data-market-mobile-chase-featured"));
  assert.ok(topChase.includes("data-market-mobile-chase-row"));
  assert.equal(/MarketSparkline|CompactSparkline|Recharts|recharts/.test(topChase), false, "no microcharts on mobile chase rows");
});

test("Top Chase keeps the approved Top 3 default with a View Top 10 expansion", () => {
  assert.ok(topChase.includes('"View Top 10"'));
  assert.ok(topChase.includes('"Show less"'));
  assert.ok(topChase.includes("MOBILE_TOP_CHASE_PREVIEW_LIMIT"));
});

test("every mobile control clears a comfortable touch target", () => {
  // Arrow functions in the props make "everything up to the first >" the wrong
  // slice, so each control is read as a fixed-length window after its tag.
  for (const [name, source] of Object.entries({ movers, topChase })) {
    let index = source.indexOf("<button");
    let seen = 0;
    while (index >= 0) {
      seen += 1;
      assert.ok(
        /min-h-11/.test(source.slice(index, index + 900)),
        `${name} has a control below the 44px touch target`
      );
      index = source.indexOf("<button", index + 1);
    }
    assert.ok(seen > 0, `${name} declares at least one control`);
  }
});

test("horizontal rails are the only horizontal scroll and the page itself never overflows", () => {
  for (const [name, source] of Object.entries({ shell, hero, movers, setValue, topChase })) {
    assert.equal(/overflow-x-scroll/.test(source), false, `${name} must not force a scrollbar`);
    assert.ok(/min-w-0/.test(source), `${name} lets its flex/grid children shrink`);
  }
});
