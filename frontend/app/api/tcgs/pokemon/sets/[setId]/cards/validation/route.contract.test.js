const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const routePath = path.resolve(__dirname, "route.js");
const source = fs.readFileSync(routePath, "utf8");

test("cards validation route defines FAILED_ANALYTICS_CACHE_CONTROL as no-store", () => {
  assert.ok(
    source.includes('const FAILED_ANALYTICS_CACHE_CONTROL = "no-store"'),
    "must define FAILED_ANALYTICS_CACHE_CONTROL = \"no-store\""
  );
});

test("cards validation route selects FAILED_ANALYTICS_CACHE_CONTROL when the backend response is not ok", () => {
  assert.ok(
    source.includes("proxyResponse.ok ? PUBLIC_ANALYTICS_CACHE_CONTROL : FAILED_ANALYTICS_CACHE_CONTROL"),
    "cache-control selection must be conditional on proxyResponse.ok"
  );
});

test("cards validation route does not hardcode public cache-control unconditionally", () => {
  const headersBlockStart = source.indexOf("return new NextResponse(payload,");
  const headersBlock = source.slice(headersBlockStart);
  assert.ok(
    !headersBlock.includes('"Cache-Control": PUBLIC_ANALYTICS_CACHE_CONTROL,'),
    "the response headers must use the conditional cacheControl variable, not a hardcoded public value"
  );
  assert.ok(headersBlock.includes('"Cache-Control": cacheControl,'), "response headers must use the cacheControl variable");
});

test("cards validation route fetch does not use Next's fetch-level cache (would cache a failed backend response for 300s)", () => {
  const fetchStart = source.indexOf("const proxyResponse = await fetch(");
  const fetchEnd = source.indexOf(");", fetchStart) + 2;
  const fetchSource = source.slice(fetchStart, fetchEnd);

  assert.ok(!fetchSource.includes("next: { revalidate"), "must not pass next: { revalidate } to fetch");
  assert.ok(fetchSource.includes('cache: "no-store"'), "must pass cache: \"no-store\" to fetch so every request re-checks the backend");
});

test("cards validation route forwards max_cards and include_plot_rows to the backend", () => {
  assert.ok(source.includes('/tcgs/pokemon/sets/${encodeURIComponent(setId)}/cards/validation'));
  assert.ok(source.includes('"max_cards"'));
  assert.ok(source.includes('"include_plot_rows"'));
  assert.ok(source.includes("backendUrl.searchParams.set(param, value)"));
});
