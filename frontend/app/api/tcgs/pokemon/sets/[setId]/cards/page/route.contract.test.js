const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const routePath = path.resolve(__dirname, "route.js");
const source = fs.readFileSync(routePath, "utf8");

test("cards page route defines one no-store cache policy for every response", () => {
  assert.ok(
    source.includes('const CARDS_PAGE_CACHE_CONTROL = "no-store"'),
    "must define CARDS_PAGE_CACHE_CONTROL = \"no-store\""
  );
  const headersBlockStart = source.indexOf("return new NextResponse(payload,");
  const headersBlock = source.slice(headersBlockStart);
  assert.ok(headersBlock.includes('"Cache-Control": CARDS_PAGE_CACHE_CONTROL,'));
  assert.ok(!source.includes("s-maxage"), "successful cards-page responses must not retain a shared-cache path");
  assert.ok(!source.includes("stale-while-revalidate"));
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
