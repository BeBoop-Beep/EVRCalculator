import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// ---------------------------------------------------------------------------
// Source contract for the redesigned DESKTOP Set Market tab.
//
// The layout rules this page was rebuilt around are structural — three separate
// sections, one movers strip, the card artwork confined to the top detail zone,
// the graph beneath it at full width — and they are the kind of rule a later
// well-meaning edit silently breaks. Recharts cannot be mounted under
// react-test-renderer (it needs a measured box and a real ResizeObserver), so
// the chart-bearing composition is pinned here, at the source level, and the
// behavioural pieces are covered by setMarketOverviewModel.test.mjs.
// ---------------------------------------------------------------------------

const here = path.dirname(fileURLToPath(import.meta.url));
// RipStatisticsPageClient.jsx carries mixed CRLF/LF line endings. Every anchor
// below spans multiple lines, so normalize before matching or the offsets slide.
const read = (relative) => fs.readFileSync(path.join(here, relative), "utf8").replace(/\r\n/g, "\n");

const page = read("../../../explore/RipStatisticsPageClient.jsx");
const model = read("./setMarketOverviewModel.mjs");

/** Comments legitimately discuss what the code must NOT do, so strip them. */
const code = (source) =>
  source
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .split("\n")
    .map((line) => line.replace(/^\s*\/\/.*$/, " "))
    .join("\n");

const DESKTOP_BRANCH_START = '{setDetailTab === "market" && isDesktopHeroComposition ? (';

function desktopMarketBranch() {
  const start = page.indexOf(DESKTOP_BRANCH_START);
  assert.notEqual(start, -1, "the desktop Market branch must still exist");
  const end = page.indexOf("{/* RETIRED:", start);
  assert.ok(end > start, "the desktop Market branch must terminate before the retired Overview block");
  return page.slice(start, end);
}

function componentSource(name) {
  const start = page.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, `${name} must exist`);
  const next = page.indexOf("\nfunction ", start + 1);
  return page.slice(start, next === -1 ? page.length : next);
}

// --- PAGE STRUCTURE ---------------------------------------------------------

test("the Market tab is exactly three sections in the approved order", () => {
  const branch = desktopMarketBranch();
  const order = [...branch.matchAll(/data-market-section="([a-z-]+)"/g)].map((match) => match[1]);
  assert.deepEqual(order, ["movers", "overview", "top-chase"]);
});

test("7D Movers stays Section 1, directly under the set header", () => {
  const branch = desktopMarketBranch();
  const moversIndex = branch.indexOf('data-market-section="movers"');
  const overviewIndex = branch.indexOf('data-market-section="overview"');
  assert.ok(moversIndex < overviewIndex, "movers must precede the market overview");
  assert.ok(branch.includes("<SevenDayMarketMoversTicker"), "Section 1 still renders the shared movers ticker");
});

test("Main Market Overview and Top 10 Chase Cards are separate modules, not one card", () => {
  const branch = desktopMarketBranch();
  assert.ok(branch.includes("<SetMarketOverviewSection"), "Section 2 exists");
  assert.ok(branch.includes("<TopChaseCardsPanel"), "Section 3 exists");
  const overviewIndex = branch.indexOf("<SetMarketOverviewSection");
  const chaseIndex = branch.indexOf("<TopChaseCardsPanel");
  assert.ok(overviewIndex < chaseIndex, "Top 10 Chase Cards sits below the market overview");
  // Each is wrapped in its own error boundary, which is only true if they are
  // genuinely separate modules rather than one merged analytics card.
  assert.ok(branch.includes('sectionName="market-overview"'));
  assert.ok(branch.includes('sectionName="market-top-chase"'));
});

test("every pre-existing Market deep link still resolves", () => {
  const branch = desktopMarketBranch();
  for (const anchorId of [
    "set-detail-market",
    "set-detail-market-movers",
    "set-detail-market-set-value",
    "set-detail-market-sealed",
    "set-detail-market-top-chase",
  ]) {
    assert.ok(branch.includes(`id="${anchorId}"`), `${anchorId} must remain addressable`);
  }
});

// --- REDUNDANCY -------------------------------------------------------------

test("there is exactly ONE movers strip on the tab, and it is not inside Top 10", () => {
  const branch = code(desktopMarketBranch());
  const moversMounts = [...branch.matchAll(/<SevenDayMarketMoversTicker/g)];
  assert.equal(moversMounts.length, 1, "a second movers strip would duplicate Section 1's purpose");

  const chase = code(componentSource("TopChaseCardsPanel"));
  assert.ok(!chase.includes("SevenDayMarketMoversTicker"), "Top 10 must not mount a movers strip");
  assert.ok(!/Top 7D Movers/i.test(chase), "Top 10 must not reintroduce a 'Top 7D Movers' strip");
  assert.ok(!/MoversTicker/.test(chase));
});

// --- MARKET VALUE TREND -----------------------------------------------------

test("the trend panel is titled Market Value Trend and offers Cards / Sealed / Graded", () => {
  const panel = componentSource("MarketValueTrendPanel");
  assert.ok(panel.includes('title="Market Value Trend"'));
  assert.ok(panel.includes("data-market-segment-tab"), "segment lenses are rendered as a control");
  assert.ok(panel.includes("MARKET_SEGMENT_LABELS"), "labels come from the shared model, not literals");
});

test("Cards is the default lens", () => {
  const section = componentSource("SetMarketOverviewSection");
  assert.match(section, /useState\("cards"\)/, "the overview opens on Cards");
});

test("the three lenses are never summed into one set total", () => {
  const section = code(componentSource("SetMarketOverviewSection"));
  const panel = code(componentSource("MarketValueTrendPanel"));
  for (const source of [section, panel]) {
    assert.ok(!/Total Set Value/i.test(source), "no combined Cards + Sealed + Graded total");
    assert.ok(!/cardsTrend\.currentValue\s*\+/.test(source), "lens values are never added together");
    assert.ok(!/sealedTrend\.currentValue\s*\+/.test(source));
  }
});

test("an unavailable lens renders an em dash, never $0", () => {
  const row = code(componentSource("MarketSegmentRow"));
  const panel = code(componentSource("MarketValueTrendPanel"));
  // The only fallback for a missing value is the em dash literal.
  assert.ok(row.includes('valueText || "—"'), "a missing segment value falls back to an em dash");
  assert.ok(panel.includes("SEGMENT_UNAVAILABLE_TEXT"), "the panel prints the shared unavailable copy");
  for (const source of [row, panel]) {
    assert.ok(!/\|\|\s*0\b/.test(source), "no numeric zero fallback for a missing market value");
    assert.ok(!/\$0/.test(source), "no literal $0 is ever rendered");
  }
});

test("an unavailable lens cannot be switched to", () => {
  const row = code(componentSource("MarketSegmentRow"));
  const panel = code(componentSource("MarketValueTrendPanel"));
  assert.ok(row.includes("if (!row.selectable)"), "an unselectable segment row is not a button");
  assert.ok(panel.includes("disabled={!row.selectable}"), "an unselectable segment tab is disabled");
});

test("Graded is declared unavailable rather than fabricated", () => {
  const section = componentSource("SetMarketOverviewSection");
  assert.ok(section.includes("unavailableSegmentTrend({ trackedItemNoun: \"Graded Cards\" })"));
  const body = code(section);
  assert.ok(!/gradedHistory|graded_history|gradedValue/.test(body), "no invented graded series");
});

test("the timeframe control offers the approved windows and drives the chart", () => {
  const panel = componentSource("MarketValueTrendPanel");
  assert.ok(panel.includes("<MarketWindowSelector"), "the shared time-range control is reused");
  assert.ok(panel.includes("windows={trend.availableDeltaWindows}"));
  // The chart is keyed on the effective window, so changing the timeframe
  // remounts the series rather than leaving a stale line on screen.
  assert.ok(panel.includes("trend.effectiveWindowKey"));
  assert.ok(panel.includes("points={trend.series}"));
});

test("the graph dominates the panel and is not reduced to a sparkline", () => {
  const panel = componentSource("MarketValueTrendPanel");
  assert.ok(panel.includes("data-market-trend-chart"));
  assert.match(panel, /data-market-trend-chart[^>]*min-h-\[20rem\]/s, "the chart keeps a substantial minimum height");
  assert.ok(!panel.includes("<MarketSparkline"), "the main trend is a chart, not a sparkline");
});

test("supporting details render the six approved fields from the active lens", () => {
  const panel = componentSource("MarketValueTrendPanel");
  assert.ok(panel.includes("Supporting Details"));
  assert.ok(panel.includes("buildSupportingDetails(trend)"), "the fields derive from the ACTIVE lens");
  for (const key of ["periodChange", "periodReturn", "periodHigh", "periodLow", "trackingSince", "trackedItems"]) {
    assert.ok(panel.includes(key), `${key} is rendered`);
  }
});

test("tracked items are counted per lens, with the lens's own noun", () => {
  const section = componentSource("SetMarketOverviewSection");
  assert.ok(section.includes('trackedItemNoun: "Cards"'));
  assert.ok(section.includes('trackedItemNoun: "Sealed Products"'));
  assert.ok(section.includes("trackedItemCount: setMarket.productCount"), "sealed counts published products");
  assert.ok(section.includes("trackedItemCount: cardsTrackedCount"));
});

// --- SET SIGNALS ------------------------------------------------------------

test("Set Signals is the right rail and carries the three approved blocks", () => {
  const rail = componentSource("SetSignalsRail");
  assert.ok(rail.includes('title="Set Signals"'));
  assert.ok(rail.includes("Market Segments"));
  assert.ok(rail.includes("data-market-breadth"));
  assert.ok(rail.includes("data-chase-concentration"));
});

test("the overview splits roughly two thirds chart to one third rail", () => {
  const section = componentSource("SetMarketOverviewSection");
  assert.match(section, /desk:grid-cols-\[minmax\(0,67fr\)_minmax\(0,33fr\)\]/);
});

test("segment rows are clickable and switch the left chart", () => {
  const rail = componentSource("SetSignalsRail");
  const row = componentSource("MarketSegmentRow");
  assert.ok(rail.includes("onSelect={onSegmentChange}"));
  assert.ok(row.includes("onClick={() => onSelect?.(row.key)}"));
  assert.ok(row.includes("aria-pressed={active}"));
  // The selected row carries the teal active treatment.
  assert.ok(row.includes("border-[var(--accent)]"));
});

test("breadth and concentration use authoritative data or render unavailable", () => {
  const section = componentSource("SetMarketOverviewSection");
  const rail = componentSource("SetSignalsRail");
  assert.ok(section.includes("selectPreparedMarketBreadth({ marketBreadth"), "breadth reads cardsMarket.marketBreadth");
  assert.ok(section.includes("selectChaseConcentration({ top10Value"), "concentration reads the published scopes");
  assert.ok(rail.includes("data-breadth-unavailable"), "breadth degrades gracefully");
  assert.ok(rail.includes("data-concentration-unavailable"), "concentration degrades gracefully");
});

test("concentration reads the published top10 scope, not a re-sum of the chase list", () => {
  const start = page.indexOf("const setValueTop10CurrentValue");
  assert.notEqual(start, -1);
  const derivation = page.slice(start, start + 600);
  assert.ok(derivation.includes("historiesByScope?.top10"), "the value comes from the published top10 scope");
  const section = code(componentSource("SetMarketOverviewSection"));
  assert.ok(!/reduce\(/.test(section), "the frontend does not re-derive the canonical figure");
});

test("no Low / Medium / High banding is invented for concentration", () => {
  const rail = code(componentSource("SetSignalsRail"));
  assert.ok(!/"(Low|Medium|High)"/.test(rail));
  assert.ok(!/concentrationBand|concentrationTier/.test(rail));
  assert.ok(!/concentrationBand|concentrationTier/.test(code(model)));
});

// --- TOP 10 CHASE CARDS -----------------------------------------------------

test("Top 10 renders a ranked list whose rows switch the detail", () => {
  const chase = componentSource("TopChaseCardsPanel");
  assert.ok(chase.includes('title="Top 10"'));
  assert.ok(chase.includes('["cards", "sealed"]'), "Top 10 exposes Cards and Sealed lenses");
  assert.ok(chase.includes("data-top-chase-list"));
  assert.ok(chase.includes("data-top-chase-row={row.rank}"));
  assert.ok(chase.includes("#{row.rank}"), "rows are ranked #1..#10");
  assert.ok(chase.includes("maxRows: 10"));
  assert.ok(chase.includes("onClick={() => setSelectedKey(row.key)}"), "clicking a row selects it");
  assert.ok(chase.includes("aria-pressed={active}"));
});

test("each Top 10 row prints the approved fields", () => {
  const chase = componentSource("TopChaseCardsPanel");
  for (const field of ["row.imageUrl", "row.name", "row.rarity", "row.priceText", "row.amountText", "row.percentText"]) {
    assert.ok(chase.includes(field), `${field} is rendered on the row`);
  }
});

test("the Top 10 split gives the detail column the larger share", () => {
  const chase = componentSource("TopChaseCardsPanel");
  assert.match(chase, /desk:grid-cols-\[minmax\(0,37fr\)_minmax\(0,63fr\)\]/);
});

// --- CARD IMAGE ASPECT RATIO ------------------------------------------------

test("the card artwork uses object-contain and never object-cover", () => {
  const frame = componentSource("CardArtworkFrame");
  assert.ok(frame.includes("object-contain"), "artwork is contained, not cropped");
  assert.ok(!frame.includes("object-cover"), "object-cover would crop the card");
  // Scoped to the redesigned Market components: the rest of this 14k-line page
  // owns unrelated surfaces (set logos, hero art) whose treatment is not this
  // pass's business.
  for (const name of ["CardArtworkFrame", "TopChaseCardsPanel", "MarketValueTrendPanel", "SetSignalsRail"]) {
    assert.ok(!code(componentSource(name)).includes("object-cover"), `${name} must not crop artwork`);
  }
});

test("the artwork's width is derived from its intrinsic ratio, never forced", () => {
  const frame = componentSource("CardArtworkFrame");
  const imgTag = frame.slice(frame.indexOf("<img"), frame.indexOf("/>", frame.indexOf("<img")));
  assert.ok(imgTag.includes("h-full"), "height drives the artwork");
  assert.ok(imgTag.includes("w-auto"), "width follows from the aspect ratio");
  // A forced width AND height together is exactly what squashes a card.
  // Match `w-full` only as its own utility. A plain \b would also fire inside
  // `max-w-full`, which is a ceiling on the artwork rather than a forced width.
  assert.ok(!/(?<![-\w])w-full/.test(imgTag), "the artwork is never stretched to the container width");
  assert.ok(!/\bwidth=/.test(imgTag) || !/\bheight=/.test(imgTag), "no forced width+height pair");
  assert.ok(imgTag.includes("max-w-full"), "the artwork never overflows its frame");
});

test("the portrait trading-card ratio is declared once and applied to the artwork", () => {
  assert.ok(page.includes('const CHASE_ARTWORK_RATIO = "63 / 88"'), "the real 63x88mm card ratio");
  const frame = componentSource("CardArtworkFrame");
  const ratioUses = [...frame.matchAll(/aspectRatio: CHASE_ARTWORK_RATIO/g)];
  assert.equal(ratioUses.length, 2, "both the frame and the image itself hold the portrait ratio");
});

test("every card image on the tab goes through the one ratio-preserving frame", () => {
  const chase = code(componentSource("TopChaseCardsPanel"));
  const imgTags = [...chase.matchAll(/<img\b/g)];
  assert.equal(imgTags.length, 0, "Top 10 must not hand-roll an <img>; it uses CardArtworkFrame");
  assert.ok(chase.includes("<CardArtworkFrame"));
});

test("the detail artwork prefers the highest-quality published image", () => {
  const chase = componentSource("TopChaseCardsPanel");
  assert.ok(chase.includes("readCardHeroImageUrl(selectedCard)"), "the detail uses the large-image reader");
  const mobileModel = read("./setMarketMobileModel.mjs");
  const reader = mobileModel.slice(mobileModel.indexOf("export function readCardHeroImageUrl"));
  assert.ok(
    reader.indexOf("imageLargeUrl") < reader.indexOf("imageSmallUrl"),
    "the large image is preferred over the thumbnail"
  );
  assert.ok(!/blur/i.test(componentSource("CardArtworkFrame")), "no artificial blur is applied");
});

// --- ZONE LAYOUT ------------------------------------------------------------

test("the selected-card artwork exists ONLY in the top detail zone", () => {
  const chase = componentSource("TopChaseCardsPanel");
  const detailStart = chase.indexOf("data-top-chase-detail");
  const zoneAStart = chase.indexOf("data-chase-detail-zone");
  const zoneBStart = chase.indexOf("data-chase-graph-zone");
  assert.ok(detailStart !== -1 && zoneAStart > detailStart, "Zone A is inside the detail column");
  assert.ok(zoneBStart > zoneAStart, "Zone B follows Zone A");

  const zoneA = chase.slice(zoneAStart, zoneBStart);
  const zoneB = chase.slice(zoneBStart);
  assert.ok(zoneA.includes("<CardArtworkFrame"), "the artwork lives in Zone A");
  assert.ok(!zoneB.includes("CardArtworkFrame"), "the artwork must not extend into the graph zone");
  assert.ok(!zoneB.includes("<img"), "the graph zone holds no image at all");
});

test("the graph sits BELOW the detail and spans the full width of the column", () => {
  const chase = componentSource("TopChaseCardsPanel");
  const zoneB = chase.slice(chase.indexOf("data-chase-graph-zone"));
  // The detail column is a vertical flex stack, so Zone B is beneath Zone A
  // rather than beside it, and it is not width-constrained.
  assert.match(chase, /data-top-chase-detail[^>]*flex min-w-0 flex-col/, "the detail column stacks vertically");
  assert.ok(zoneB.includes("flex-1"), "the graph takes the remaining height of the module");
  // Same boundary care as above: `min-w-0` is a flex-shrink guard, not a width.
  assert.ok(!/(?<![-\w])w-\d/.test(zoneB.slice(0, 200)), "the graph zone has no fixed width");
  assert.ok(zoneB.includes("<SetValueLineChart"), "the graph is the shared Market chart");
});

test("the chase graph uses the same window machinery as the rest of the tab", () => {
  const chase = componentSource("TopChaseCardsPanel");
  assert.ok(chase.includes("selectSegmentTrend({ history, selectedWindowKey"), "same selected-period logic");
  assert.ok(chase.includes("<MarketWindowSelector"), "same time controls");
  assert.ok(chase.includes("changeAmount={cardTrend.deltaAmount}"));
  assert.ok(chase.includes("changePercent={cardTrend.deltaPercent}"));
});

// --- RESPONSIVE -------------------------------------------------------------

test("both grids collapse to a single column below the desktop breakpoint", () => {
  for (const name of ["SetMarketOverviewSection", "TopChaseCardsPanel"]) {
    const source = componentSource(name);
    assert.match(source, /grid-cols-1[^"]*desk:grid-cols-\[/, `${name} stacks before it splits`);
  }
});

test("the artwork keeps its portrait ratio at every width", () => {
  const frame = componentSource("CardArtworkFrame");
  // The ratio is unconditional — there is no responsive variant that drops it,
  // and no width utility that could override the height-driven sizing.
  assert.ok(!/(sm|md|desk|lg):(w-full|object-cover|aspect-)/.test(frame));
  const chase = componentSource("TopChaseCardsPanel");
  // Frames are sized by height utilities only (h-12, h-40, desk:h-48).
  const frameUses = [...chase.matchAll(/<CardArtworkFrame[\s\S]*?\/>/g)].map((match) => match[0]);
  assert.ok(frameUses.length >= 2);
  for (const use of frameUses) {
    const className = /className="([^"]*)"/.exec(use)?.[1] || "";
    assert.ok(/\bh-\d/.test(className), "each frame is sized by height");
    assert.ok(!/(?<![-\w])w-full/.test(className), "no frame is stretched to full width");
  }
});

// --- NO REGRESSION OUTSIDE THE REDESIGN -------------------------------------

test("the redesign does not touch publication, scoring or scraper surfaces", () => {
  const branch = code(desktopMarketBranch());
  for (const forbidden of ["ripDecision", "canonicalRip", "financialRip", "publication", "scrape"]) {
    assert.ok(!new RegExp(forbidden, "i").test(branch), `Market must not reach into ${forbidden}`);
  }
});

test("the other set-detail tabs are untouched by the Market branch", () => {
  const branch = desktopMarketBranch();
  assert.ok(!branch.includes("<RipDecisionPage"));
  assert.ok(!branch.includes("PullRates"));
  assert.ok(page.includes("<RipDecisionPage"), "the RIP tab still renders elsewhere on the page");
});

test("the mobile Market composition still mounts and is unchanged by this pass", () => {
  assert.ok(page.includes("<SetMarketMobile"), "the below-1200px composition is untouched");
  const start = page.indexOf('{setDetailTab === "market" ? (');
  const mobileBranch = page.slice(start, page.indexOf(DESKTOP_BRANCH_START));
  assert.ok(mobileBranch.includes("isDesktopHeroComposition ? null : ("), "exactly one composition mounts at a time");
});

// ---------------------------------------------------------------------------
// REGRESSION LOCK — desktop Top 10 permanent master-detail layout.
//
// An earlier pass briefly collapsed the desktop list to a Top-3-plus-disclosure
// pattern (the correct behaviour for MOBILE, borrowed from
// SetMarketMobileTopChase, but never approved for desktop). These tests pin
// the corrected desktop contract so that regression cannot silently return.
// ---------------------------------------------------------------------------

test("desktop Top 10 has no collapsed state: no View Top 10, no Show more/less, no expand toggle", () => {
  const chase = code(componentSource("TopChaseCardsPanel"));
  assert.ok(!/View Top 10/i.test(chase), "View Top 10 is a mobile-only disclosure and must not appear on desktop");
  assert.ok(!/Show \d+ more|Show less|Show all/i.test(chase), "no progressive-disclosure copy on desktop");
  assert.ok(!/useState\(false\)/.test(chase) || !/expanded|showAll/i.test(chase), "no expanded/showAll state on desktop");
  assert.ok(!chase.includes("aria-expanded"), "desktop has no disclosure button to expand");
});

test("desktop Top 10 always renders all ten rows with no row slice", () => {
  const chase = componentSource("TopChaseCardsPanel");
  assert.ok(chase.includes("maxRows: 10"), "the model is built for all ten rows");
  // rows.map is used directly on the full list — no .slice(...) gating a preview.
  assert.ok(!/rows\.slice\(/.test(code(chase)), "desktop must not slice the row list down to a preview");
  assert.match(chase, /\{rows\.map\(\(row\)/, "every row in the model is rendered");
});

test("the master-detail proportions target the approved 35-40 / 60-65 split", () => {
  const chase = componentSource("TopChaseCardsPanel");
  assert.match(chase, /desk:grid-cols-\[minmax\(0,37fr\)_minmax\(0,63fr\)\]/, "37/63 sits inside the approved 35-40/60-65 range");
});

test("selecting any of the ten rows updates the right-hand detail, never navigates away", () => {
  const chase = code(componentSource("TopChaseCardsPanel"));
  assert.ok(chase.includes("onClick={() => setSelectedKey(row.key)}"), "a click sets local selection state");
  assert.ok(!/window\.location|router\.push|<a\s+href/.test(chase), "no row is a navigation link");
});

test("the selected-card graph renders only inside the right pane, never beneath the list", () => {
  const chase = componentSource("TopChaseCardsPanel");
  const listStart = chase.indexOf("data-top-chase-list");
  const detailStart = chase.indexOf("data-top-chase-detail");
  const graphStart = chase.indexOf("data-chase-graph-zone");
  assert.ok(listStart < detailStart && detailStart < graphStart, "list, then detail column, then graph inside it");
  // The list and detail column are two cells of the same grid row — the graph
  // living inside the detail column's own flex stack is what keeps it out from
  // underneath the list.
  assert.match(chase, /grid-cols-1[^"]*desk:grid-cols-\[minmax\(0,37fr\)_minmax\(0,63fr\)\][^>]*>/s);
});
