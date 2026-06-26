import test from "node:test";
import assert from "node:assert/strict";

import {
  buildFallbackSetPagePayload,
  fetchWithTimeout,
  getRecoverableExplorePayload,
  isSetPageRequestTimeoutPayload,
  sanitizeBackendPath,
  withStaleSetPageDiagnostics,
} from "./explorePageServerCore.mjs";

test("set page fallback payload includes selected target identity and diagnostics", () => {
  const payload = buildFallbackSetPagePayload({
    targetId: "set-1",
    fallbackTarget: {
      target_id: "set-1",
      id: "set-1",
      name: "Known Set",
      slug: "known-set",
      canonical_key: "knownSet",
      summary: { pack_score: 82 },
    },
    status: 500,
    elapsedMs: 3001,
    backendPath: "/tcgs/pokemon/sets/set-1/page",
    bodyPreview: "backend failed",
  });

  assert.equal(payload.summary.target_id, "set-1");
  assert.equal(payload.summary.name, "Known Set");
  assert.equal(payload.summary.pack_score, 82);
  assert.equal(payload.meta.fallback, true);
  assert.equal(payload.meta.sources.setPage, "fallback");
  assert.match(payload.meta.warnings[0], /fallback shell/);
  assert.equal(payload.meta.errors[0].code, "SET_PAGE_PAYLOAD_UNAVAILABLE");
  assert.equal(payload.meta.errors[0].status, 500);
  assert.equal(payload.meta.errors[0].backendPath, "/tcgs/pokemon/sets/set-1/page");
});

test("set page timeout fallback is marked retryable and not backend missing", () => {
  const payload = buildFallbackSetPagePayload({
    targetId: "set-1",
    elapsedMs: 3001,
    backendPath: "/tcgs/pokemon/sets/set-1/page",
    code: "SET_PAGE_PAYLOAD_TIMEOUT",
    message: "Explore page fetch timed out after 3000ms",
    requestTimeout: true,
  });

  assert.equal(payload.meta.requestTimeout, true);
  assert.equal(payload.meta.fallbackReason, "request_timeout");
  assert.equal(payload.meta.sources.setPage, "timeout_fallback");
  assert.match(payload.meta.warnings[0], /request timed out; retrying/);
  assert.equal(isSetPageRequestTimeoutPayload(payload), true);
});

test("explicit missing snapshot fallback is not marked as timeout", () => {
  const payload = buildFallbackSetPagePayload({
    targetId: "set-1",
    status: 404,
    backendPath: "/tcgs/pokemon/sets/set-1/page",
    code: "SET_PAGE_PAYLOAD_NOT_FOUND",
  });

  assert.equal(payload.meta.requestTimeout, false);
  assert.equal(payload.meta.fallbackReason, "snapshot_missing");
  assert.equal(isSetPageRequestTimeoutPayload(payload), false);
});

test("recoverable set page payload returns stale success on later backend error", () => {
  const stale = getRecoverableExplorePayload({
    targetType: "set",
    targetId: "set-1",
    staleEntry: {
      staleExpiresAt: Date.now() + 60_000,
      data: {
        summary: { target_id: "set-1", name: "Cached Set", pack_score: 91 },
        meta: { warnings: [], sources: { setPage: "pokemon_set_page_snapshot_latest" } },
      },
    },
    status: 500,
    elapsedMs: 2500,
    backendPath: "/tcgs/pokemon/sets/set-1/page",
  });

  assert.equal(stale.summary.name, "Cached Set");
  assert.equal(stale.summary.pack_score, 91);
  assert.equal(stale.meta.stale, true);
  assert.equal(stale.meta.sources.setPage, "stale_cache");
  assert.match(stale.meta.warnings.at(-1), /Using stale set page payload/);
  assert.equal(stale.meta.errors.at(-1).code, "SET_PAGE_PAYLOAD_STALE_FALLBACK");
});

test("recoverable fallback is set-page only", () => {
  const payload = getRecoverableExplorePayload({
    targetType: "sealed",
    targetId: "box-1",
    status: 500,
    backendPath: "/explore/page",
  });

  assert.equal(payload, null);
});

test("stale set page diagnostics preserve payload and append error", () => {
  const payload = withStaleSetPageDiagnostics(
    {
      summary: { target_id: "set-1", name: "Cached Set" },
      top_hits: [{ name: "Chase" }],
      meta: { warnings: ["existing warning"], sources: { setPage: "snapshot" } },
    },
    {
      status: 503,
      elapsedMs: 123,
      backendPath: "/tcgs/pokemon/sets/set-1/page",
    }
  );

  assert.equal(payload.top_hits.length, 1);
  assert.equal(payload.meta.warnings[0], "existing warning");
  assert.equal(payload.meta.stale, true);
  assert.equal(payload.meta.errors.at(-1).status, 503);
});

test("backend path sanitizer does not expose origin or query string", () => {
  const path = sanitizeBackendPath("https://secret.example.internal/tcgs/pokemon/sets/set-1/page?token=super-secret");

  assert.equal(path, "/tcgs/pokemon/sets/set-1/page");
});

test("fetchWithTimeout aborts slow fetches", async () => {
  await assert.rejects(
    fetchWithTimeout(
      "https://example.invalid/slow",
      {},
      5,
      (_url, options) =>
        new Promise((_resolve, reject) => {
          options.signal.addEventListener("abort", () => reject(new Error("aborted")));
        })
    ),
    /timed out/
  );
});
