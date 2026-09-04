import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const SOURCE_PATH = new URL("./ripStatisticsServer.js", import.meta.url);
const source = readFileSync(SOURCE_PATH, "utf8").replace(/\r\n/g, "\n");

// The backend builds the ENTIRE target cohort regardless of `limit` and then
// truncates (verified 2026-08-12: meta.timings is byte-identical for limit=5
// and limit=200, and limit=5 is an exact prefix of limit=200). So a per-limit
// cache key buys nothing but costs a second ~1.6s cold backend computation
// whenever a caller asking for 60 is followed by a caller asking for 150 —
// which is exactly the Rankings -> Set navigation.
test("entitlement-sensitive cohorts have no cross-request process cache", () => {
  assert.doesNotMatch(source, /targetsCache|inflightRequests|rip-statistics-targets/);
  assert.match(source, /getBackendRequestAuthHeaders\(request\)/);
});

// Production stability effort (2026-09-04): the publicOnly cohort (fixed
// Accept-only headers, identical response for every anonymous/Base/Plus/
// Premium visitor) is the ONE deliberate exception — it now gets a bounded
// process cache + in-flight join so the Homepage doesn't re-hit the backend
// on every request. The authenticated path above must remain untouched.
test("only the publicOnly cohort gets a bounded cache; the authenticated path is untouched", () => {
  assert.match(source, /if \(!publicOnly\) \{\s*\n\s*return _fetchRipStatisticsTargetsUncached\(request, \{ publicOnly: false \}\);/);
  assert.match(source, /const PUBLIC_COHORT_KEY = "public";/);
  assert.match(source, /COHORT_TTL_MS/);
});

test("the single upstream fetch always requests the canonical full cohort", () => {
  assert.ok(
    source.includes("const CANONICAL_COHORT_LIMIT = MAX_TARGETS_LIMIT;"),
    "there must be one canonical cohort size"
  );
  assert.ok(
    source.includes('url.searchParams.set("limit", String(CANONICAL_COHORT_LIMIT));'),
    "the upstream request must always ask for the canonical cohort, never the caller's limit"
  );
});

test("callers still receive at most the number of targets they asked for", () => {
  assert.ok(
    /targets: cohort\.targets\.slice\(0, limit\)/.test(source),
    "the requested limit must be applied by slicing the shared cohort"
  );
});

test("slicing never mutates the caller-scoped cohort", () => {
  const start = source.indexOf("export async function getRipStatisticsTargets");
  const body = source.slice(start);
  assert.ok(body.includes("...cohort"), "must return a fresh payload object per caller");
  assert.ok(!/cohort\.targets\.length = /.test(body), "must not truncate the cached array in place");
  assert.ok(!/cohort\.targets\.splice\(/.test(body), "must not splice the cached array");
});

test("the requested limit is still reflected back in meta.request", () => {
  assert.ok(
    source
      .slice(source.indexOf("export async function getRipStatisticsTargets"))
      .includes("request: { ...(cohort.meta?.request || {}), limit }"),
    "meta.request.limit must report what the caller asked for, not the canonical cohort size"
  );
});

test("only one freshness boundary remains", () => {
  // Historical constraint: a Next data-cache TTL stacked on top of this process
  // TTL could keep a superseded snapshot visible unpredictably longer.
  assert.ok(source.includes('cache: "no-store"'), "upstream fetch must stay uncached by Next");
  assert.equal(
    (source.match(/next:\s*\{\s*revalidate/g) || []).length,
    0,
    "must not reintroduce a second revalidate TTL"
  );
});
