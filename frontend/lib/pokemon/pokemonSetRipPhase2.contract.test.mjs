import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const route = fs.readFileSync(new URL("../../app/TCGs/Pokemon/Sets/[setSlug]/page.js", import.meta.url), "utf8");
const snapshots = fs.readFileSync(new URL("./pokemonSetInitialSnapshotsServer.js", import.meta.url), "utf8");
const client = fs.readFileSync(new URL("../../components/explore/RipStatisticsPageClient.jsx", import.meta.url), "utf8");

test("direct RIP uses directory plus shell/bootstrap and not full targets", () => {
  assert.match(route, /activeSetDetailTab === "overview" \|\| activeSetDetailTab === "market"/);
  assert.match(snapshots, /wantsRipBootstrap \? getPokemonSetRipBootstrapInitialSnapshot/);
  assert.doesNotMatch(snapshots.slice(snapshots.indexOf("export async function getPokemonSetInitialSnapshots")), /wantsSimulationEvidence/);
});

test("RIP dead requests retain dedicated tab owners", () => {
  assert.match(client, /if \(setDetailTab !== "pull-rates"\)/);
  assert.match(client, /const shouldFetchTopChase = setDetailTab === "market" && marketCriticalSettled/);
  const enabled = client.slice(client.indexOf("const insightsFetchEnabled ="), client.indexOf(";", client.indexOf("const insightsFetchEnabled =")));
  assert.match(enabled, /setDetailTab === "insights"/);
  assert.doesNotMatch(enabled, /setDetailTab === "overview"/);
});

test("bootstrap owns RIP score, decision and calculation run", () => {
  assert.match(client, /resolveCanonicalRipV7\(ripBootstrap\?\.canonicalSource, explorePayload/);
  assert.match(client, /ripBootstrap\?\.ripDecision \?\? explorePayload\?\.ripDecision/);
  assert.match(client, /ripBootstrap\?\.calculationRunId \?\? activeTarget/);
  assert.match(client, /compatibleRipGlobalContext\?\.productFamilyRankings/);
});
