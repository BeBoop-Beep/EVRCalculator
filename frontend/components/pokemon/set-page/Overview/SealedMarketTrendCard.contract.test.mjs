import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const card = readFileSync(new URL("./SealedMarketTrendCard.jsx", import.meta.url), "utf8");
const tooltip = readFileSync(new URL("../../../explore/MarketTrendTooltipCard.jsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../../../../app/styles/globals.css", import.meta.url), "utf8");
const picker = readFileSync(new URL("./SealedProductPicker.jsx", import.meta.url), "utf8");

test("sealed presentation uses one title and selector product label", () => {
  assert.match(card, /<h2 className="text-lg font-semibold leading-normal text-\[var\(--text-primary\)\]">Sealed Market<\/h2>/);
  assert.doesNotMatch(card, /desk:text-sm/);
  // The product selector moved from a native <select> into SealedProductPicker,
  // so the label contract is asserted where it now lives: the concise label is
  // what renders, and the full scraped name stays in title/aria-label only.
  assert.doesNotMatch(card, /<option|<select/);
  assert.match(picker, /<span className="min-w-0 flex-1 truncate">\{label\}<\/span>/);
  assert.match(picker, /title=\{item\.name\}/);
  assert.match(picker, /aria-label=\{`\$\{label\}, \$\{item\.name\}, \$\{price\}/);
  assert.doesNotMatch(card, /<p[^>]*title=\{product\.name\}>\{product\.name\}<\/p>/);
});

test("the card leads with the market value, then product, then time, then chart", () => {
  // The value is the insight and leads. The product is the analytical subject
  // and the window is a filter applied to it, so the product stays ABOVE the
  // 1D–LT controls: value → product → time → chart.
  const at = (needle) => {
    const index = card.indexOf(needle);
    assert.ok(index > 0, `expected to locate ${needle}`);
    return index;
  };
  const title = at("Sealed Market</h2>");
  const value = at("<MarketValueChange");
  const product = at("<SealedProductPicker");
  const window = at("<MarketWindowSelector");
  const chart = at("<ChartFrame");
  const asOf = card.indexOf("As of", chart);

  assert.ok(title < value, "the value follows the title");
  assert.ok(value < product, "the value precedes the product selector");
  assert.ok(product < window, "the product precedes the time-window controls");
  assert.ok(window < chart, "the window controls stay directly above the chart");
  assert.ok(asOf > chart, "the as-of note stays last");

  // Each element appears exactly once — no duplicate mobile/desktop
  // composition, and no CSS `order` utility faking a different visual order.
  for (const needle of ["<MarketValueChange", "<SealedProductPicker", "<MarketWindowSelector", "<ChartFrame"]) {
    assert.equal(card.split(needle).length - 1, 1, `${needle} must be mounted once`);
  }
  assert.doesNotMatch(card, /\border-\d|\bflex-col-reverse\b/);

  // No duplicate product subtitle and no new label above the value: the
  // section title already supplies the context.
  assert.doesNotMatch(card, /Current Product Value|Selected product/);
  const summary = card.slice(value, product);
  assert.doesNotMatch(summary, /\{product\.name\}<\/p>|<h3|<p[^>]*>\{product\.name\}/);
});

test("the card stacks its layers on a consistent 12px rhythm", () => {
  assert.match(card, /<div data-sealed-market-summary className="mt-3">\n\s*<MarketValueChange/);
  assert.match(card, /<MarketWindowSelector[\s\S]*?className="mt-3"/);
  assert.match(card, /<ChartFrame className="mt-3 /);
  // Value → selector spacing comes from the picker's own root wrapper.
  assert.match(picker, /className="relative mt-3 min-w-0"/);

  // Same rhythm at every breakpoint — no per-breakpoint margin overrides.
  assert.doesNotMatch(card, /(md|lg|desk|sm):mt-/);

  // Layout only: dimensions, padding and typography are untouched.
  assert.match(card, /<ChartFrame className="mt-3 h-32 overflow-hidden rounded-xl md:h-36 lg:h-32">/);
  assert.match(card, /className=\{`set-glass-surface relative min-w-0 overflow-visible rounded-2xl border border-\[var\(--border-subtle\)\] p-4 /);
  assert.match(card, /<h2 className="text-lg font-semibold leading-normal text-\[var\(--text-primary\)\]">/);
  assert.match(picker, /h-10 w-full min-w-0 items-center justify-between gap-2 rounded-lg pl-2 pr-3 text-xs/);
  assert.match(card, /variant="chart-summary"/);
  // No divider was introduced between the internal layers.
  assert.doesNotMatch(card.slice(card.indexOf("<MarketValueChange"), card.indexOf("<ChartFrame")), /<hr|border-t/);
});

test("reordering did not disturb product selection or the no-refetch contract", () => {
  assert.match(card, /<SealedProductPicker\n\s*products=\{orderedProducts\}\n\s*value=\{product\.sealedProductId\}\n\s*onChange=\{setSelectedId\}\n\s*onOpenChange=\{setPickerOpen\}\n\s*\/>/);
  assert.match(card, /sortSealedProductsByCurrentPrice\(state\.payload\?\.products\)/);
  assert.match(card, /selectSealedProduct\(state\.payload, selectedId\)/);
  // The fetch effect still keys on the set only, so switching products and
  // windows re-reads the loaded payload rather than refetching.
  assert.match(card, /\}, \[setId, retryKey\]\);/);
  assert.doesNotMatch(card, /<select|<option/);
});

test("sealed chart shares the dark tooltip and Set Value ombre language", () => {
  assert.match(card, /<ComposedChart/);
  assert.match(card, /<Area type="linear" dataKey="marketPrice"/);
  assert.match(card, /useId\(\)\.replace\(\/:\/g, ""\)/);
  assert.match(card, /NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR/);
  assert.match(card, /trendDirection === "positive"[\s\S]*POSITIVE_VALUE_COLOR[\s\S]*trendDirection === "negative"[\s\S]*NEGATIVE_VALUE_COLOR[\s\S]*NEUTRAL_MARKET_COLOR/);
  assert.match(card, /stopColor=\{trendColor\} stopOpacity="0\.13"/);
  assert.match(card, /stopColor=\{trendColor\} stopOpacity="0\.035"/);
  assert.equal((card.match(/stroke=\{trendColor\}/g) || []).length, 2);
  assert.match(card, /fill: trendColor/);
  assert.match(card, /<feGaussianBlur stdDeviation="1\.8" \/>/);
  assert.match(card, /content=\{<SealedMarketTooltip \/>}/);
  const tooltipBlock = card.slice(card.indexOf("<Tooltip"), card.indexOf("/>", card.indexOf("<Tooltip")));
  assert.doesNotMatch(tooltipBlock, /formatter=\{|labelFormatter=/);
  assert.match(tooltip, /bg-\[rgba\(2,6,23,0\.96\)\]/);
  assert.match(tooltip, /changeAmount=\{numberOrNull\(deltaAmount\)\}/);
  assert.match(tooltip, /changePercent=\{numberOrNull\(deltaPercent\)\}/);
  assert.match(card, /<Line type="linear" dataKey="marketPrice"/);
});

test("mobile divider keeps its restrained three-pixel footprint after the luminous pass", () => {
  // The flat single-token fill became a layered luminous hairline; the 3px
  // decorative box (and so the section separation) is unchanged.
  assert.match(css, /--mobile-section-divider-core: rgba\(226, 232, 240, 0\.28\)/);
  assert.match(css, /--mobile-section-divider-core: rgba\(71, 85, 105, 0\.22\)/);
  assert.match(css, /\[data-mobile-section\]::before\s*\{[^}]*height: 3px;/s);
});
