import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("./RipStatisticsPageClient.jsx", import.meta.url),
  "utf8"
);
const css = readFileSync(
  new URL("../../app/styles/globals.css", import.meta.url),
  "utf8"
);

test("mobile set header scroll tracking mounts without pointer or focus activation", () => {
  assert.match(source, /window\.addEventListener\("scroll", updateFromScroll, \{ passive: true \}\)/);
  assert.doesNotMatch(source, /isSetContextFocusWithin/);
  assert.doesNotMatch(source, /document\.addEventListener\("focus(?:in|out)"/);
});

test("mobile set header uses cumulative hide and reveal hysteresis", () => {
  assert.match(source, /MOBILE_SET_MENU_HIDE_DISTANCE_PX = 10/);
  assert.match(source, /MOBILE_SET_MENU_REVEAL_DISTANCE_PX = 56/);
  assert.match(source, /scrollState\.cumulativeDownwardPx \+= delta/);
  assert.match(source, /scrollState\.cumulativeUpwardPx \+= Math\.abs\(delta\)/);
  assert.match(source, /scrollState\.cumulativeDownwardPx = 0;\s+if \(!isMobileSetContextHiddenRef/s);
  assert.match(source, /scrollState\.cumulativeUpwardPx = 0;\s+scrollState\.cumulativeDownwardPx \+= delta/s);
});

test("mobile set header listener and animation frame are cleaned up", () => {
  assert.match(source, /window\.removeEventListener\("scroll", updateFromScroll\)/);
  assert.match(source, /window\.cancelAnimationFrame\(frameId\)/);
});

test("mobile set header animation is transform-based and reduced-motion safe", () => {
  assert.match(css, /transform 280ms cubic-bezier\(0\.22, 1, 0\.36, 1\)/);
  assert.match(css, /translate3d\(0, calc\(-100% - 1px\), 0\)/);
  assert.match(css, /opacity: 0;/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.set-detail-sticky-tabs \{\s+transition: none;/);
});
