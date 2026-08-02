import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const card = readFileSync(new URL("./SealedMarketTrendCard.jsx", import.meta.url), "utf8");
const tooltip = readFileSync(new URL("../../../explore/MarketTrendTooltipCard.jsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../../../../app/styles/globals.css", import.meta.url), "utf8");

test("sealed presentation uses one title and selector product label", () => {
  assert.match(card, /<h2 className="text-lg font-semibold leading-normal text-\[var\(--text-primary\)\]">Sealed Market<\/h2>/);
  assert.doesNotMatch(card, /desk:text-sm/);
  assert.match(card, /<option[^>]*>\{compactSealedProductLabel\(item\)\}[^<]*\{item\.name\}<\/option>/);
  assert.doesNotMatch(card, /<p[^>]*title=\{product\.name\}>\{product\.name\}<\/p>/);
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

test("mobile divider opacity is reduced and its three-pixel rule remains", () => {
  assert.match(css, /--mobile-section-divider: rgba\(226, 232, 240, 0\.30\)/);
  assert.match(css, /--mobile-section-divider: rgba\(100, 116, 139, 0\.25\)/);
  assert.match(css, /\[data-mobile-section\]::before\s*\{[^}]*height: 3px;/s);
});
