import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8");
const hub = read("./CardRankingsHub.jsx");
const collector = read("./CardCollectorAppealRankings.jsx");
const chase = read("./CardChaseEfficiencyRankings.jsx");
const lazy = read("./RankingsLazyClient.jsx");
const service = read("../../../backend/db/services/card_collector_appeal_query_service.py");

test("Cards removes only the selector context-card and preserves controls", () => {
  assert.match(hub, /data-card-ranking-mode-control/);
  assert.doesNotMatch(hub, /data-card-ranking-mode-control[^>]*set-glass-surface/);
  for (const label of ["Collector Appeal", "Chase Efficiency"]) assert.ok(hub.includes(label));
  for (const lens of ["overall", "pokemon", "trainer", "artist", "playability"]) assert.ok(collector.includes(`value: "${lens}"`));
  assert.match(hub, /variant="rankings"|<SegmentedControl/);
});

test("auth resolving is neither a lock nor an empty/error result", () => {
  assert.match(hub, /authStatus === "resolving"/);
  assert.match(hub, /Checking card access/);
  assert.match(hub, /authStatus !== "resolving" && lens/);
});

test("identity transition remounts Cards and access loss clears protected state", () => {
  assert.match(lazy, /<CardRankingsHub key=\{sessionCache\.identity\}/);
  assert.match(collector, /if \(!entitled\)[\s\S]*setResults\(\{\}\)/);
  assert.match(chase, /if \(!entitled\)[\s\S]*setResult\(\{ status: "idle", payload: null \}\)/);
  assert.match(collector, /requestGeneration\.current \+= 1/);
  assert.match(chase, /requestGeneration\.current \+= 1/);
});

test("latest request generation wins and local retry preserves same-query last-good", () => {
  for (const source of [collector, chase]) {
    assert.match(source, /generation === requestGeneration\.current/);
    assert.match(source, /forceRetry\.current = true/);
    assert.match(source, /showing the last successful result/);
    assert.match(source, />Retry</);
  }
  assert.match(collector, /Retry filters/);
});

test("global component rank and page-first bounded enrichment remain unchanged", () => {
  assert.match(service, /get_pokemon_card_component_rankings_v1/);
  assert.match(service, /rankSemantics.*global_component_cohort/);
  assert.match(service, /card_ids = \[.*ranking_rows/);
  assert.match(service, /\.in_\("id", card_ids\)/);
  assert.doesNotMatch(collector, /rows\.(sort|filter)\(/);
});
