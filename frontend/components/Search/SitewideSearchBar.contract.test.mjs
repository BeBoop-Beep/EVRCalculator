import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("./SitewideSearchBar.jsx", import.meta.url), "utf8");
const route = await readFile(new URL("../../app/api/search/route.js", import.meta.url), "utf8");

test("header typeahead is debounced, abortable, stale-safe, and preserves free-text fallback", () => {
  assert.match(source, /}, 275\)/);
  assert.match(source, /new AbortController\(\)/);
  assert.match(source, /requestId !== requestRef\.current/);
  assert.match(source, /activeIndex >= 0.*choose\(items\[activeIndex\]\).*submit\(\)/s);
  assert.match(source, /event\.key === "ArrowDown"/);
  assert.match(source, /event\.key === "ArrowUp"/);
  assert.match(source, /event\.key === "Escape"/);
  assert.match(source, /role="combobox"/);
  assert.match(source, /role="listbox"/);
  assert.match(source, /role="option"/);
});

test("browser calls one normalized site-search boundary", () => {
  assert.match(source, /fetch\(`\/api\/search\?q=/);
  assert.match(route, /new URL\("\/search", getBackendApiBaseUrl\(\)\)/);
  assert.doesNotMatch(source, /market\/explorer\/instruments\/search/);
});
