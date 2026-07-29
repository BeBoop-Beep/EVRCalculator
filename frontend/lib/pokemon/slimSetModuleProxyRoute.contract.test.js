const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const proxyPath = path.resolve(__dirname, "slimSetModuleProxyRoute.js");
const source = fs.readFileSync(proxyPath, "utf8").replace(/\r\n/g, "\n");

// One implementation now backs /overview, /market/top-chase, /market/movers and
// /market/value-history, so these guarantees are asserted once here instead of
// being copy-pasted into four route contract tests.

test("the shared slim proxy bounds a stalled backend read", () => {
  assert.ok(source.includes("new AbortController()"), "must use AbortController for a bounded timeout");
  assert.ok(
    source.includes("setTimeout(() => controller.abort(), BACKEND_FETCH_TIMEOUT_MS)"),
    "must abort the backend fetch on the shared timeout"
  );
  assert.ok(source.includes("signal: controller.signal"), "must pass the abort signal to fetch");
  assert.ok(source.includes("clearTimeout(timeout)"), "must clear the timer so a fast response leaks nothing");
});

test("a stalled or failed backend read returns a structured, uncached error", () => {
  assert.ok(source.includes("buildSlimSetModuleProxyErrorBody"), "must return the structured error body");
  assert.ok(source.includes("slimSetModuleProxyErrorStatus(timedOut)"), "must map timeout/transport failure to 504/502");
  assert.ok(
    source.includes('headers: { "Cache-Control": FAILED_ANALYTICS_CACHE_CONTROL }'),
    "a failed response must be no-store"
  );
  assert.ok(source.includes("backendPathForDiagnostics(backendUrl)"), "must include the backend path in diagnostics");
});

test("a normal backend response is passed through untouched", () => {
  // A slow-but-successful read must stay a success with its own status and
  // body — the timeout must never be turned into an empty 200.
  assert.ok(source.includes("status: proxyResponse.status"), "must preserve the backend status");
  assert.ok(source.includes("const payload = await proxyResponse.text()"), "must preserve the backend body verbatim");
  assert.ok(
    source.includes("proxyResponse.ok ? PUBLIC_ANALYTICS_CACHE_CONTROL : FAILED_ANALYTICS_CACHE_CONTROL"),
    "cache-control must stay conditional on proxyResponse.ok"
  );
  assert.ok(!source.includes("next: { revalidate"), "must not opt into Next's fetch cache");
  assert.ok(source.includes('cache: "no-store"'), "the backend fetch must bypass Next's fetch cache");
});

test("a missing set id is rejected before any backend call", () => {
  assert.ok(source.includes('code: "SET_ID_REQUIRED"'));
  const guardIndex = source.indexOf('code: "SET_ID_REQUIRED"');
  const fetchIndex = source.indexOf("await fetch(");
  assert.ok(guardIndex >= 0 && fetchIndex > guardIndex, "the set-id guard must precede the backend fetch");
});
