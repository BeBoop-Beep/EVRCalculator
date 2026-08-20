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
const sealed = read("./SetMarketMobileSealed.jsx");
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

test("the mobile composition renders the five sections in the required order", () => {
  const order = ["SetMarketMobileHero", "SetMarketMobileMovers", "SetMarketMobileSetValue", "SetMarketMobileTopChase", "SetMarketMobileSealed"];
  const positions = order.map((name) => shell.indexOf(`<${name}`));
  assert.ok(positions.every((position) => position > 0), "every section is mounted");
  assert.deepEqual(positions, [...positions].sort((left, right) => left - right), "hero → movers → set value → top chase → sealed");
});

test("each mobile section is independently boundaried so one failure cannot take the tab down", () => {
  assert.equal((shell.match(/<SectionErrorBoundary\b/g) || []).length, 5);
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

test("desktop Market keeps its own four production modules untouched", () => {
  for (const moduleName of ["SetValueTrendCard", "TopChaseCardsModule", "SevenDayMarketMoversTicker", "SealedMarketTrendCard"]) {
    assert.equal(
      (marketBranch.match(new RegExp(`<${moduleName}\\b`, "g")) || []).length,
      1,
      `${moduleName} is still mounted exactly once, by the desktop branch only`
    );
    assert.equal(shell.includes(moduleName), false, `${moduleName} is not re-mounted by the mobile composition`);
  }
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
  const sources = { shell, hero, movers, setValue, topChase, sealed, model };
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
  for (const [name, raw] of Object.entries({ hero, movers, setValue, topChase, sealed, model })) {
    const source = code(raw);
    for (const forbidden of ["Market Cap", "market_cap", "marketCap", "Population", "populationCount", "Raw Copies", "Print Run", "printRun"]) {
      assert.equal(source.includes(forbidden), false, `${name} must not claim ${forbidden}`);
    }
  }
});

test("Set Value owns its own timeframe control and no page-level master toggle is added", () => {
  assert.ok(setValue.includes("<MarketWindowSelector"), "Set Value carries its own window selector");
  assert.ok(topChase.includes("<MarketWindowSelector"), "Top Chase carries its own window selector");
  assert.ok(sealed.includes("<MarketWindowSelector"), "Sealed carries its own window selector");
  // The shell is composition only — it must not hoist a shared timeframe.
  assert.equal(/WindowSelector|TimeRangeSelector|windowKey/.test(shell), false, "the tab has no master timeframe");
});

test("Set Value reads the same selectors the desktop card reads", () => {
  assert.ok(setValue.includes("selectSetValueTrendFromContract"));
  assert.ok(setValue.includes("selectOverviewSetValueTrendByScope"));
  // No local arithmetic on a value, delta or window.
  assert.equal(/currentValue\s*[-+*/]/.test(setValue), false, "Set Value computes nothing of its own");
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

test("Sealed Market stays its own section with real product switching", () => {
  assert.equal(setValue.includes("Sealed"), false, "sealed is never folded into the Set Value card");
  assert.ok(sealed.includes('title="Sealed Market"'));
  assert.ok(sealed.includes("data-market-mobile-sealed-products"));
  assert.ok(sealed.includes("chips.length > 1"), "a single-product set renders no dead chip row");
  assert.ok(sealed.includes("getPokemonSetSealedMarket"), "the same slim sealed request backs both compositions");
  assert.ok(sealed.includes("selectSealedProduct") && sealed.includes("selectSealedWindow"));
});

test("every mobile control clears a comfortable touch target", () => {
  // Arrow functions in the props make "everything up to the first >" the wrong
  // slice, so each control is read as a fixed-length window after its tag.
  for (const [name, source] of Object.entries({ movers, topChase, sealed })) {
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
  for (const [name, source] of Object.entries({ shell, hero, movers, setValue, topChase, sealed })) {
    assert.equal(/overflow-x-scroll/.test(source), false, `${name} must not force a scrollbar`);
    assert.ok(/min-w-0/.test(source), `${name} lets its flex/grid children shrink`);
  }
});
