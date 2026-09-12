import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("./SitewideSearchBar.jsx", import.meta.url), "utf8");
const route = await readFile(new URL("../../app/api/search/route.js", import.meta.url), "utf8");

test("header typeahead is debounced, abortable, stale-safe, and preserves free-text fallback", () => {
  assert.match(source, /needle\.length === 2 \? 225 : 175/);
  assert.match(source, /new AbortController\(\)/);
  assert.match(source, /requestId !== requestRef\.current/);
  assert.match(source, /activeIndex >= 0.*choose\(items\[activeIndex\]\).*submit\(\)/s);
  assert.match(source, /event\.key === "ArrowDown"/);
  assert.match(source, /event\.key === "ArrowUp"/);
  assert.match(source, /event\.key === "Escape"/);
  assert.match(source, /role="combobox"/);
  assert.match(source, /role="listbox"/);
  assert.match(source, /role="option"/);
  assert.match(source, /resultCacheRef = useRef\(new Map\(\)\)/);
  assert.match(source, /resultCacheRef\.current\.size > 20/);
});

test("browser calls one normalized site-search boundary", () => {
  assert.match(source, /fetch\(`\/api\/search\?q=/);
  assert.match(route, /new URL\("\/search", getBackendApiBaseUrl\(\)\)/);
  assert.doesNotMatch(source, /market\/explorer\/instruments\/search/);
  assert.match(route, /let stage = "resolve-backend-url"/);
  assert.match(route, /Server-Timing/);
  assert.match(route, /\[api\/search\] failed/);
});

test("card and set results use fixed decorative optimized thumbnails with set fallback", () => {
  assert.match(source, /item\.resultType === "card"/);
  assert.match(source, /item\.resultType === "set"/);
  assert.match(source, /CARD_THUMBNAIL_WIDTH/);
  assert.match(source, /SET_LOGO_THUMBNAIL_WIDTH/);
  assert.match(source, /optimizedImageUrl\(source, width\)/);
  assert.match(source, /\[item\.imageUrl, item\.imageFallbackUrl\]\.filter\(Boolean\)/);
  assert.match(source, /onError=\{\(\) => setCandidateIndex/);
  assert.match(source, /alt="" loading="lazy" decoding="async"/);
  assert.match(source, /h-\[50px\] w-9/);
  assert.match(source, /h-9 w-12/);
  assert.match(source, /min-w-0 flex-1/);
  assert.equal((source.match(/fetch\(/g) || []).length, 1);
});
