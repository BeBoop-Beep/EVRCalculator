const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const routePath = path.resolve(__dirname, "route.js");
const source = fs.readFileSync(routePath, "utf8");

test("cards page route defines FAILED_ANALYTICS_CACHE_CONTROL as no-store", () => {
  assert.ok(
    source.includes('const FAILED_ANALYTICS_CACHE_CONTROL = "no-store"'),
    "must define FAILED_ANALYTICS_CACHE_CONTROL = \"no-store\""
  );
});

test("cards page route selects FAILED_ANALYTICS_CACHE_CONTROL when the backend response is not ok", () => {
  assert.ok(
    source.includes("proxyResponse.ok ? PUBLIC_ANALYTICS_CACHE_CONTROL : FAILED_ANALYTICS_CACHE_CONTROL"),
    "cache-control selection must be conditional on proxyResponse.ok"
  );
});

test("cards page route does not hardcode public cache-control unconditionally", () => {
  const headersBlockStart = source.indexOf("return new NextResponse(payload,");
  const headersBlock = source.slice(headersBlockStart);
  assert.ok(
    !headersBlock.includes('"Cache-Control": PUBLIC_ANALYTICS_CACHE_CONTROL,'),
    "the response headers must use the conditional cacheControl variable, not a hardcoded public value"
  );
  assert.ok(headersBlock.includes('"Cache-Control": cacheControl,'), "response headers must use the cacheControl variable");
});

test("cards page route fetch does not use Next's fetch-level cache (would cache a failed backend response for 300s)", () => {
  const fetchStart = source.indexOf("const proxyResponse = await fetch(");
  const fetchEnd = source.indexOf(");", fetchStart) + 2;
  const fetchSource = source.slice(fetchStart, fetchEnd);

  assert.ok(!fetchSource.includes("next: { revalidate"), "must not pass next: { revalidate } to fetch");
  assert.ok(fetchSource.includes('cache: "no-store"'), "must pass cache: \"no-store\" to fetch so every request re-checks the backend");
});

test("cards page route forwards page, page_size, sort, q, rarity, movement_filter, movement_sort to the backend", () => {
  assert.ok(source.includes('/tcgs/pokemon/sets/${encodeURIComponent(setId)}/cards/page'));
  assert.ok(source.includes('"page"'));
  assert.ok(source.includes('"page_size"'));
  assert.ok(source.includes('"sort"'));
  assert.ok(source.includes('"q"'));
  assert.ok(source.includes('"rarity"'));
  assert.ok(source.includes('"movement_filter"'));
  assert.ok(source.includes('"movement_sort"'));
  assert.ok(source.includes("backendUrl.searchParams.set(param, value)"));
});
