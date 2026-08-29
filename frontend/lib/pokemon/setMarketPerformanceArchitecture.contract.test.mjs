import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const route = fs.readFileSync(new URL("../../app/TCGs/Pokemon/Sets/[setSlug]/page.js", import.meta.url), "utf8");
const snapshots = fs.readFileSync(new URL("./pokemonSetInitialSnapshotsServer.js", import.meta.url), "utf8");
const client = fs.readFileSync(new URL("../../components/explore/RipStatisticsPageClient.jsx", import.meta.url), "utf8");
const sealedHook = fs.readFileSync(new URL("../../hooks/pokemon/usePokemonSetSealedMarket.js", import.meta.url), "utf8");
const marketClient = fs.readFileSync(new URL("./pokemonSetMarketClient.js", import.meta.url), "utf8");
const signalsHook = fs.readFileSync(new URL("../../hooks/pokemon/usePokemonSetMarketSignals.js", import.meta.url), "utf8");

test("Market and RIP routes use the slim route directory", () => {
  assert.match(route, /getPokemonSetRouteDirectory\(\{ limit: 150 \}\)/);
  assert.match(route, /requestedTargetType === "set"[\s\S]*getPokemonSetInitialSnapshots/);
});

test("Market server seed uses the dedicated bootstrap projection", () => {
  assert.match(snapshots, /market\/bootstrap/);
  assert.match(snapshots, /getPokemonSetMarketBootstrapInitialSnapshot/);
  assert.match(snapshots, /wantsMarketSeed \? getPokemonSetMarketBootstrapInitialSnapshot/);
});

test("a valid Market bootstrap seed suppresses immediate duplicate overview fetch", () => {
  assert.match(client, /seededOverviewPayload && overviewRetryNonce === 0/);
  assert.match(client, /overview\.seed_satisfied_initial_resource/);
});

test("the visible 365d Top Chase preview is seeded and suppresses its first duplicate fetch", () => {
  assert.match(snapshots, /market\/top-chase[\s\S]*url\.searchParams\.set\("window", "365d"\)[\s\S]*url\.searchParams\.set\("limit", "10"\)/);
  assert.match(client, /if \(seededTopChasePayload && topChaseRetryNonce === 0\) return undefined/);
});

test("consumer sealed is opt-in and uses a bounded completed-resource cache", () => {
  assert.match(sealedHook, /requestVersion === 0/);
  assert.match(sealedHook, /return \{ \.\.\.state, retry, load \}/);
  assert.match(marketClient, /market\/sealed-consumer/);
  assert.match(marketClient, /CONSUMER_SEALED_CACHE_MAX_ENTRIES = 8/);
  assert.match(marketClient, /while \(consumerSealedCache\.size > CONSUMER_SEALED_CACHE_MAX_ENTRIES\)/);
});

test("legacy and consumer Sealed transports remain distinct", () => {
  assert.match(marketClient, /sealed-legacy:\$\{resolvedSetId\}/);
  assert.match(marketClient, /sealed-consumer:\$\{resolvedSetId\}/);
  assert.match(sealedHook, /getPokemonSetConsumerSealedMarket/);
});

test("paid Market signals use a separate authenticated no-store request", () => {
  assert.match(client, /usePokemonSetMarketSignals/);
  assert.match(signalsHook, /getPokemonSetMarketSignals/);
  assert.match(marketClient, /market\/signals/);
  assert.match(marketClient, /cache: "no-store"/);
});

test("desktop and mobile share the bounded Market Signals retry hook", () => {
  const mobile = fs.readFileSync(new URL("../../components/pokemon/set-page/Market/SetMarketMobile.jsx", import.meta.url), "utf8");
  assert.match(client, /usePokemonSetMarketSignals\(setId/);
  assert.match(mobile, /usePokemonSetMarketSignals\(setId/);
  assert.match(signalsHook, /attempt === 0 && isRetryableMarketSignalsError/);
  assert.match(signalsHook, /setTimeout\(\(\) => load\(1\)/);
  assert.match(signalsHook, /status: error\?\.status === 403 \? "forbidden" : "error"/);
  assert.match(signalsHook, /payload: null/);
  assert.match(signalsHook, /cancelled/);
  assert.match(signalsHook, /return \{ \.\.\.state, retry \}/);
});

test("Market Signals request normalizes window for URL and request key", () => {
  assert.match(marketClient, /market-signals:\$\{resolvedSetId\}:\$\{normalizedWindow\}/);
  assert.match(marketClient, /URLSearchParams\(\{ window: normalizedWindow \}\)/);
});

test("bootstrap concentration summary survives normalization", () => {
  assert.match(marketClient, /chaseConcentration/);
  assert.match(client, /seededOverviewPayload\?\.chaseConcentration\?\.top10/);
});
