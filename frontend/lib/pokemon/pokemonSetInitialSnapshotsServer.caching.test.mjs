import assert from "node:assert/strict";
import test from "node:test";
import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const snapshotsServerPath = path.resolve(__dirname, "pokemonSetInitialSnapshotsServer.js");

// ---------------------------------------------------------------------------
// Revalidation constants
// ---------------------------------------------------------------------------

test("CARDS_SNAPSHOT_REVALIDATE_S no longer exists – cards snapshots do not use Next's data cache", () => {
  const source = fs.readFileSync(snapshotsServerPath, "utf8");

  // Full set card checklists can exceed Next's 2MB data-cache entry size limit,
  // which spammed "Failed to set Next.js data cache" warnings on every request.
  assert.ok(!source.includes("CARDS_SNAPSHOT_REVALIDATE_S"), "must not define or reference CARDS_SNAPSHOT_REVALIDATE_S");
});

test("MARKET_DASHBOARD_SNAPSHOT_REVALIDATE_S no longer exists – market dashboard snapshots do not use Next's data cache", () => {
  const source = fs.readFileSync(snapshotsServerPath, "utf8");

  // Market dashboard snapshots can exceed Next's 2MB data-cache entry size limit,
  // same root cause as cards (see the CARDS_SNAPSHOT_REVALIDATE_S test above).
  assert.ok(!source.includes("MARKET_DASHBOARD_SNAPSHOT_REVALIDATE_S"), "must not define or reference MARKET_DASHBOARD_SNAPSHOT_REVALIDATE_S");
});

// ---------------------------------------------------------------------------
// loadInitialSnapshot – fetch options
// ---------------------------------------------------------------------------

test("loadInitialSnapshot builds next cache options when nextCacheOptions is provided", () => {
  const source = fs.readFileSync(snapshotsServerPath, "utf8");

  assert.ok(source.includes("nextCacheOptions = null"), "must accept nextCacheOptions param (defaulting to null)");
  assert.ok(source.includes("next: nextCacheOptions"), "must spread nextCacheOptions into next: when provided");
  assert.ok(source.includes('cache: "no-store"'), "must fall back to cache: no-store when nextCacheOptions is null");
});

test("loadInitialSnapshot does not hardcode cache: no-store in the fetch call – it is only the fallback", () => {
  const source = fs.readFileSync(snapshotsServerPath, "utf8");

  // The fetch call now uses a variable (fetchOpts), not a hardcoded { cache: "no-store" }
  assert.ok(source.includes("fetchWithTimeout(url.toString(), fetchOpts"), "fetch call must pass fetchOpts variable");
  assert.ok(!source.includes("fetchWithTimeout(url.toString(), {\n"), "fetch call must not inline the options object directly");
});

// ---------------------------------------------------------------------------
// getPokemonSetCardsInitialSnapshot – cache options
// ---------------------------------------------------------------------------

test("getPokemonSetCardsInitialSnapshot does not pass nextCacheOptions (falls back to cache: no-store)", () => {
  const source = fs.readFileSync(snapshotsServerPath, "utf8");
  const fnStart = source.indexOf("export async function getPokemonSetCardsInitialSnapshot");
  const fnEnd = source.indexOf("export async function getPokemonSetMarketDashboardInitialSnapshot", fnStart);
  const fnSource = source.slice(fnStart, fnEnd);

  assert.ok(!fnSource.includes("nextCacheOptions:"), "cards snapshot must not pass nextCacheOptions to loadInitialSnapshot");
  assert.ok(!fnSource.includes("revalidate:"), "cards snapshot must not request Next revalidation");
  assert.ok(!fnSource.includes("pokemon-set-cards:"), "cards snapshot must not tag a Next cache entry that can't hold >2MB payloads");
});

// ---------------------------------------------------------------------------
// getPokemonSetMarketDashboardInitialSnapshot – cache options
// ---------------------------------------------------------------------------

test("getPokemonSetMarketDashboardInitialSnapshot does not pass nextCacheOptions (falls back to cache: no-store)", () => {
  const source = fs.readFileSync(snapshotsServerPath, "utf8");
  const fnStart = source.indexOf("export async function getPokemonSetMarketDashboardInitialSnapshot");
  const fnEnd = source.indexOf("export async function getPokemonSetInitialSnapshots", fnStart);
  const fnSource = source.slice(fnStart, fnEnd);

  assert.ok(!fnSource.includes("nextCacheOptions:"), "market dashboard snapshot must not pass nextCacheOptions to loadInitialSnapshot");
  assert.ok(!fnSource.includes("revalidate:"), "market dashboard snapshot must not request Next revalidation");
  assert.ok(!fnSource.includes("pokemon-set-market-dashboard:"), "market dashboard snapshot must not tag a Next cache entry that can't hold >2MB payloads");
});

// ---------------------------------------------------------------------------
// No-store is gone from normal paths (not hardcoded in callers)
// ---------------------------------------------------------------------------

test("getPokemonSetCardsInitialSnapshot caller does not hardcode cache: no-store", () => {
  const source = fs.readFileSync(snapshotsServerPath, "utf8");
  const fnStart = source.indexOf("export async function getPokemonSetCardsInitialSnapshot");
  const fnEnd = source.indexOf("export async function getPokemonSetMarketDashboardInitialSnapshot", fnStart);
  const fnSource = source.slice(fnStart, fnEnd);

  assert.ok(!fnSource.includes('cache: "no-store"'), "cards caller must not hardcode cache: no-store");
});

test("getPokemonSetMarketDashboardInitialSnapshot caller does not hardcode cache: no-store", () => {
  const source = fs.readFileSync(snapshotsServerPath, "utf8");
  const fnStart = source.indexOf("export async function getPokemonSetMarketDashboardInitialSnapshot");
  const fnEnd = source.indexOf("export async function getPokemonSetInitialSnapshots", fnStart);
  const fnSource = source.slice(fnStart, fnEnd);

  assert.ok(!fnSource.includes('cache: "no-store"'), "market dashboard caller must not hardcode cache: no-store");
});

// ---------------------------------------------------------------------------
// Fallback / error shape is unchanged
// ---------------------------------------------------------------------------

test("loadInitialSnapshot error and fallback return shapes are unchanged", () => {
  const source = fs.readFileSync(snapshotsServerPath, "utf8");
  const fnStart = source.indexOf("async function loadInitialSnapshot(");
  const fnEnd = source.indexOf("export async function getPokemonSetCardsInitialSnapshot", fnStart);
  const fnSource = source.slice(fnStart, fnEnd);

  assert.ok(fnSource.includes("payload: null"), "error return must include payload: null");
  assert.ok(fnSource.includes("serializeError(error, url, elapsedMs)"), "network error path must call serializeError");
  assert.ok(fnSource.includes("if (!response.ok)"), "must check response.ok");
  assert.ok(fnSource.includes("payload: normalizePayload ? normalizePayload("), "success path must normalize payload");
});

test("getPokemonSetInitialSnapshots still aggregates errors and timings unchanged", () => {
  const source = fs.readFileSync(snapshotsServerPath, "utf8");
  const fnStart = source.indexOf("export async function getPokemonSetInitialSnapshots");
  const fnSource = source.slice(fnStart);

  assert.ok(fnSource.includes("errors.cards"), "must still set errors.cards on card failure");
  assert.ok(fnSource.includes("errors.marketDashboard"), "must still set errors.marketDashboard on market failure");
  assert.ok(fnSource.includes("cardsPayload: cards.payload"), "must still return cardsPayload");
  assert.ok(fnSource.includes("marketDashboardPayload: marketDashboard.payload"), "must still return marketDashboardPayload");
  assert.ok(fnSource.includes("timings:"), "must still return timings");
});
