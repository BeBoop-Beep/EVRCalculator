import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./RipStatisticsPageClient.jsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../../app/styles/globals.css", import.meta.url), "utf8");

function between(startToken, endToken) {
  const start = source.indexOf(startToken);
  const end = source.indexOf(endToken, start);
  assert.ok(start >= 0 && end > start);
  return source.slice(start, end);
}

test("Set Value Trend has no redundant current-value eyebrow in either data branch", () => {
  const card = between('title="Set Value Trend"', "<SetValueLineChart");
  assert.doesNotMatch(card, />Current \{selectedMetricLabel\}</);
  assert.match(card, /bodySpacingClassName="mt-2"/);
  assert.doesNotMatch(card, /<MarketValueChange\s+className="mt-1"/);
  assert.match(source, /bodySpacingClassName = "mt-4"/);
});

test("desktop title card rises above its sibling tabs only while its picker is open", () => {
  assert.match(
    source,
    /data-set-context-header\s+data-set-picker-open=\{isDesktopHeroComposition && heroSetPickerOpen \? "true" : "false"\}/
  );
  assert.match(css, /\[data-set-context-header\] \{[\s\S]*?z-index: 2;[\s\S]*?overflow: visible;/);
  assert.match(
    css,
    /\[data-set-context-header\]\[data-set-picker-open="true"\] \{\s+z-index: 50;\s+\}/
  );
  assert.match(css, /\.set-detail-sticky-tabs \{[\s\S]*?z-index: 40;/);
});

test("desktop dropdown remains absolute, scrollable, and interactive above the tabs", () => {
  const desktopPicker = between("data-compact-set-picker", "className=\"min-w-0 border-t");
  assert.match(desktopPicker, /absolute left-0 top-\[calc\(100%\+0\.5rem\)\]/);
  assert.match(desktopPicker, /overflow-y-auto/);
  assert.match(desktopPicker, /onClick=\{\(\) => handleHeroSetSelect\(target\)\}/);
  assert.doesNotMatch(desktopPicker, /pointer-events-none|overflow-hidden|overflow-clip/);
});
