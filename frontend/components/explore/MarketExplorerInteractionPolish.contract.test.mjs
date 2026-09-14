import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8").replace(/\r\n/g, "\n");

test("Reference Market remains a focusable prepared toggle with stable scroll geometry", () => {
  const option = read("./ExplorerMarketOption.jsx");
  const builder = read("./MarketExplorerQueryBuilder.jsx");
  const active = read("./MarketExplorerActiveMarkets.jsx");
  const reference = builder.slice(builder.indexOf('id="cardsReference"'), builder.indexOf("</ExplorerDisclosure>", builder.indexOf('id="cardsReference"')));

  assert.match(option, /type="checkbox"/);
  assert.match(option, /onChange=\{\(\) => onToggle\?\.\(entry\.key\)\}/);
  assert.match(reference, /PreparedOptionList entries=\{benchmarkEntries\} onToggle=\{onToggleBenchmark\}/);
  assert.match(active, /<ul className="flex min-w-max flex-nowrap gap-1\.5">/);
  assert.match(active, /series\.length <= 1 \? "invisible pointer-events-none"/);
  assert.doesNotMatch(active, /series\.length > 1 \? \(/);
  for (const source of [option, reference, active]) {
    assert.doesNotMatch(source, /scrollIntoView|scrollTo\(|location\.hash|href="#|preventDefault/);
    assert.doesNotMatch(source, /fetch\(|axios|onAddQuery|builder\.replace/);
  }
});

test("shared chart portals one measured tooltip positioned from the snapped guide", () => {
  const chart = read("./MarketPerformanceChart.jsx");
  assert.match(chart, /positionMarketPerformanceTooltip/);
  assert.match(chart, /crosshairX: tooltipAnchor\.bounds\.width \* \(xAt\(activeIndex\) \/ VIEW_WIDTH\)/);
  assert.match(chart, /element\.getBoundingClientRect\(\)/);
  assert.match(chart, /element\.scrollHeight/);
  assert.match(chart, /new ResizeObserver\(measure\)/);
  assert.match(chart, /createPortal\(/);
  assert.match(chart, /document\.body/);
  assert.match(chart, /pointer-events-none fixed/);
  assert.doesNotMatch(chart, /tooltipAnchor\.top - 10/);
  assert.doesNotMatch(chart, /translate\(-50%, -100%\)/);
  assert.doesNotMatch(chart, /fetch\(|axios/);
});

test("pointer, keyboard, touch, scroll, and resize all feed the shared placement", () => {
  const chart = read("./MarketPerformanceChart.jsx");
  assert.match(chart, /selectAtPointer\(event\.clientX, event\.clientY\)/);
  assert.match(chart, /anchorFromBounds\(bounds, "keyboard"\)/);
  assert.match(chart, /event\.key === "ArrowRight" \|\| event\.key === "ArrowLeft"/);
  assert.match(chart, /event\.key === "Escape"/);
  assert.match(chart, /classifyPointerGesture/);
  assert.match(chart, /kind === "scroll"/);
  assert.match(chart, /window\.addEventListener\("scroll", reanchor, true\)/);
  assert.match(chart, /window\.addEventListener\("resize", reanchor\)/);
});

test("Market and Explorer inherit the same tooltip implementation", () => {
  const market = read("./PokemonMarketPerformance.jsx");
  const explorer = read("./MarketExplorerChart.jsx");
  assert.match(market, /<MarketPerformanceChart/);
  assert.match(explorer, /<MarketPerformanceChart/);
  assert.doesNotMatch(market, /positionMarketPerformanceTooltip/);
  assert.doesNotMatch(explorer, /positionMarketPerformanceTooltip/);
});
