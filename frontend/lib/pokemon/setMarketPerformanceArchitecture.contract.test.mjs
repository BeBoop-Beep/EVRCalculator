import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const route = fs.readFileSync(new URL("../../app/TCGs/Pokemon/Sets/[setSlug]/page.js", import.meta.url), "utf8");
const snapshots = fs.readFileSync(new URL("./pokemonSetInitialSnapshotsServer.js", import.meta.url), "utf8");
const client = fs.readFileSync(new URL("../../components/explore/RipStatisticsPageClient.jsx", import.meta.url), "utf8");
const sealedHook = fs.readFileSync(new URL("../../hooks/pokemon/usePokemonSetSealedMarket.js", import.meta.url), "utf8");
const marketClient = fs.readFileSync(new URL("./pokemonSetMarketClient.js", import.meta.url), "utf8");

test("Market route uses the slim route directory while RIP retains Rankings targets", () => {
  assert.match(route, /activeSetDetailTab === "market"[\s\S]*getPokemonSetRouteDirectory/);
  assert.match(route, /:[\s\S]*getRipStatisticsTargets/);
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

test("consumer sealed is opt-in and uses a bounded completed-resource cache", () => {
  assert.match(sealedHook, /requestVersion === 0/);
  assert.match(sealedHook, /return \{ \.\.\.state, retry, load \}/);
  assert.match(marketClient, /market\/sealed-consumer/);
  assert.match(marketClient, /CONSUMER_SEALED_CACHE_MAX_ENTRIES = 8/);
  assert.match(marketClient, /while \(consumerSealedCache\.size > CONSUMER_SEALED_CACHE_MAX_ENTRIES\)/);
});
