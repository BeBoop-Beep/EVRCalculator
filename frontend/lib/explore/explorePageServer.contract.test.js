const fs = require("fs");
const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");

const serverPath = path.resolve(__dirname, "explorePageServer.js");
const setRoutePath = path.resolve(__dirname, "../../app/TCGs/Pokemon/Sets/[setSlug]/page.js");

test("getExplorePagePayload set fetch uses timeout and recoverable fallback instead of route-killing throw", () => {
  const source = fs.readFileSync(serverPath, "utf8");
  const fetchStart = source.indexOf("res = await fetchWithTimeout");
  const catchStart = source.indexOf("} catch (networkErr) {", fetchStart);
  const nonOkStart = source.indexOf("if (!res.ok) {", fetchStart);
  const jsonParseStart = source.indexOf("try {\n      payload = await res.json();", nonOkStart);

  assert.ok(source.includes("SET_PAGE_FETCH_TIMEOUT_MS"));
  assert.ok(fetchStart >= 0);
  assert.ok(catchStart > fetchStart);
  assert.ok(nonOkStart > fetchStart);
  assert.ok(jsonParseStart > nonOkStart);
  assert.ok(source.slice(catchStart, nonOkStart).includes("getRecoverableExplorePayload"));
  assert.ok(source.slice(nonOkStart, jsonParseStart).includes("getRecoverableExplorePayload"));
  assert.ok(source.includes("code: isTimeout ? \"SET_PAGE_PAYLOAD_TIMEOUT\" : \"SET_PAGE_PAYLOAD_NETWORK_ERROR\""));
  assert.ok(source.includes("code: \"SET_PAGE_PAYLOAD_BACKEND_ERROR\""));
  assert.ok(source.includes("source: recoverablePayload.meta?.stale ? \"stale_cache\" : \"fallback\""));
});

test("getExplorePagePayload stores stale success cache and sanitizes backend diagnostics", () => {
  const source = fs.readFileSync(serverPath, "utf8");

  assert.ok(source.includes("staleExpiresAt: now + STALE_TTL_MS"));
  assert.ok(source.includes("const backendPath = sanitizeBackendPath(url);"));
  assert.ok(source.includes("bodyPreview = previewResponseBody(body);"));
  assert.ok(!source.includes("console.error(\"[explore-page-server] fetch_error\", {\n        targetType,\n        targetId,\n        status: res.status,\n        body,"));
});

test("set page route passes selectedTarget into fallbackTarget", () => {
  const source = fs.readFileSync(setRoutePath, "utf8");

  assert.ok(source.includes("fallbackTarget: selectedTarget"));
});
