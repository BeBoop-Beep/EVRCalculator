import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const lazy = fs.readFileSync(new URL("./RankingsLazyClient.jsx", import.meta.url), "utf8");

test("lazy Rankings requests cannot self-abort when loading state changes", () => {
  assert.doesNotMatch(lazy, /\[lens, eraLens, eraState\.status/);
  assert.doesNotMatch(lazy, /\[lens, setsState\.status/);
  assert.match(lazy, /if \(!active\) return;/);
  assert.doesNotMatch(lazy, /AbortError" \? "unavailable"/);
});

test("leaving and returning to Sets creates a fresh request and exposes Retry", () => {
  assert.match(lazy, /if \(lens !== "sets"\) return undefined;[\s\S]*new AbortController\(\)/);
  assert.match(lazy, /setSetsRetry\(\(value\) => value \+ 1\)/);
  assert.match(lazy, /payload\.targets\.length > 0 \? "ready" : "unavailable"/);
  assert.match(lazy, /setsCache\.current\.get\(cacheKey\)/);
});

test("all lazy Rankings requests have a bounded timeout", () => {
  assert.equal((lazy.match(/12000/g) || []).length, 2);
});

test("auth transitions are identity-scoped and distinguish locked from broken", () => {
  assert.match(lazy, /authStatus !== "resolved"/);
  assert.match(lazy, /const cacheKey = `\$\{requestKey\}:/);
  assert.match(lazy, /status: "locked"/);
  assert.match(lazy, /Index Plus or Premium/);
  assert.match(lazy, /Request timed out/);
});
